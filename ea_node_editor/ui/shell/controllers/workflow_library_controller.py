# Purpose: Own project/global custom-workflow library state and publication.
# Map: feature_routes/workflow_library_drop_connect
# Tests: tests/test_workflow_library_controller.py
from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from ea_node_editor.custom_workflows import (
    custom_workflow_library_items,
    find_custom_workflow_definition,
    load_global_custom_workflow_definitions,
    normalize_custom_workflow_metadata,
    save_global_custom_workflow_definitions,
    upsert_custom_workflow_definition,
)
from ea_node_editor.graph.hierarchy import scope_parent_id
from ea_node_editor.graph.transforms import build_subnode_custom_workflow_snapshot_data
from ea_node_editor.nodes.builtins.subnode import SUBNODE_TYPE_ID
from ea_node_editor.ui.shell.controllers.dialog_support import resolve_dialog_parent
from ea_node_editor.ui.shell.controllers.result import ControllerResult
from ea_node_editor.ui.shell.controllers.workspace_selection_context import (
    WorkspaceSelectionContext,
)
from ea_node_editor.ui.shell.runtime_clipboard import (
    build_graph_fragment_payload,
    normalize_graph_fragment_payload,
)

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.window import ShellWindow

_CUSTOM_WORKFLOW_DESCRIPTION = "Project-local custom workflow snapshot."
_WORKFLOW_SCOPE_LOCAL = "local"
_WORKFLOW_SCOPE_GLOBAL = "global"


def _published_workflow_id(shell_node_id: object) -> str:
    normalized_shell_node_id = str(shell_node_id or "").strip()
    return f"wf_shell_{normalized_shell_node_id}" if normalized_shell_node_id else ""


class WorkflowLibraryController:
    def __init__(
        self,
        host: ShellWindow,
        selection_context: WorkspaceSelectionContext,
    ) -> None:
        self._host = host
        self._selection_context = selection_context
        self._shown_global_migration_report: tuple[str, ...] = ()

    def project_metadata(self) -> dict[str, Any]:
        metadata = self._host.model.project.metadata
        if isinstance(metadata, dict):
            return metadata
        self._host.model.project.replace_metadata({})
        return self._host.model.project.metadata

    def custom_workflow_definitions(self) -> list[dict[str, Any]]:
        metadata = self.project_metadata()
        normalized = normalize_custom_workflow_metadata(metadata.get("custom_workflows"))
        if metadata.get("custom_workflows") != normalized:
            updated_metadata = dict(metadata)
            updated_metadata["custom_workflows"] = normalized
            self._host.model.project.replace_metadata(updated_metadata)
        return normalized

    def set_custom_workflow_definitions(self, definitions: list[dict[str, Any]]) -> None:
        metadata = self.project_metadata()
        updated_metadata = dict(metadata)
        updated_metadata["custom_workflows"] = normalize_custom_workflow_metadata(definitions)
        self._host.model.project.replace_metadata(updated_metadata)

    def global_custom_workflow_definitions(self) -> list[dict[str, Any]]:
        from PyQt6.QtWidgets import QMessageBox

        migration_report: list[str] = []
        try:
            definitions = load_global_custom_workflow_definitions(
                registry=self._host.registry,
                migration_report=migration_report,
            )
        except ValueError as exc:
            message = str(exc)
            report = (message,)
            if report != self._shown_global_migration_report:
                self._shown_global_migration_report = report
                QMessageBox.warning(
                    resolve_dialog_parent(self._host),
                    "Custom Workflow Migration Failed",
                    message,
                )
            return []
        report = tuple(migration_report)
        if report and report != self._shown_global_migration_report:
            self._shown_global_migration_report = report
            QMessageBox.information(
                resolve_dialog_parent(self._host),
                "Custom Workflow Migration",
                "\n".join(report),
            )
        return normalize_custom_workflow_metadata(definitions)

    @staticmethod
    def set_global_custom_workflow_definitions(definitions: list[dict[str, Any]]) -> None:
        save_global_custom_workflow_definitions(definitions)

    @staticmethod
    def upsert_workflow_definition_by_id(
        definitions: list[dict[str, Any]],
        definition: dict[str, Any],
    ) -> list[dict[str, Any]]:
        workflow_id = str(definition.get("workflow_id", "")).strip()
        if not workflow_id:
            return definitions
        normalized = normalize_custom_workflow_metadata(definitions)
        for index, existing in enumerate(normalized):
            if str(existing.get("workflow_id", "")).strip() != workflow_id:
                continue
            normalized[index] = copy.deepcopy(definition)
            return normalized
        normalized.append(copy.deepcopy(definition))
        return normalize_custom_workflow_metadata(normalized)

    @staticmethod
    def rename_workflow_definition_by_id(
        definitions: list[dict[str, Any]],
        workflow_id: str,
        new_name: str,
    ) -> list[dict[str, Any]] | None:
        normalized_workflow_id = str(workflow_id or "").strip()
        normalized_name = str(new_name or "").strip()
        if not normalized_workflow_id or not normalized_name:
            return None
        normalized = normalize_custom_workflow_metadata(definitions)
        for index, existing in enumerate(normalized):
            if str(existing.get("workflow_id", "")).strip() != normalized_workflow_id:
                continue
            updated = copy.deepcopy(existing)
            updated["name"] = normalized_name
            normalized[index] = updated
            return normalize_custom_workflow_metadata(normalized)
        return None

    def custom_workflow_library_items(self) -> list[dict[str, Any]]:
        local_items = custom_workflow_library_items(self.custom_workflow_definitions())
        for item in local_items:
            item["workflow_scope"] = _WORKFLOW_SCOPE_LOCAL

        global_items = custom_workflow_library_items(self.global_custom_workflow_definitions())
        for item in global_items:
            item["workflow_scope"] = _WORKFLOW_SCOPE_GLOBAL

        local_ids = {str(item.get("workflow_id", "")).strip() for item in local_items}
        merged_items = list(local_items)
        global_only_items = [
            item
            for item in global_items
            if str(item.get("workflow_id", "")).strip() not in local_ids
        ]
        merged_items.extend(global_only_items)
        merged_items.sort(
            key=lambda item: (
                str(item.get("display_name", "")).lower(),
                str(item.get("workflow_id", "")).lower(),
            )
        )
        return merged_items

    def resolve_custom_workflow_definition(self, workflow_id: str) -> dict[str, Any] | None:
        normalized_workflow_id = str(workflow_id or "").strip()
        if not normalized_workflow_id:
            return None
        local_definition = find_custom_workflow_definition(
            self.custom_workflow_definitions(),
            normalized_workflow_id,
        )
        if local_definition is not None:
            return local_definition
        global_definition = find_custom_workflow_definition(
            self.global_custom_workflow_definitions(),
            normalized_workflow_id,
        )
        if global_definition is not None:
            return global_definition
        return None

    def set_custom_workflow_scope(
        self,
        workflow_id: str,
        workflow_scope: str,
    ) -> ControllerResult[bool]:
        normalized_workflow_id = str(workflow_id or "").strip()
        target_scope = str(workflow_scope or "").strip().lower()
        if not normalized_workflow_id:
            return ControllerResult(False, "No custom workflow ID provided.", payload=False)
        if target_scope not in {_WORKFLOW_SCOPE_LOCAL, _WORKFLOW_SCOPE_GLOBAL}:
            return ControllerResult(False, "Custom workflow scope is invalid.", payload=False)

        local_definitions = self.custom_workflow_definitions()
        global_definitions = self.global_custom_workflow_definitions()

        if target_scope == _WORKFLOW_SCOPE_GLOBAL:
            definition = find_custom_workflow_definition(local_definitions, normalized_workflow_id)
            if definition is None:
                return ControllerResult(False, "Project custom workflow not found.", payload=False)
            remaining_local = [
                item
                for item in local_definitions
                if str(item.get("workflow_id", "")).strip() != normalized_workflow_id
            ]
            updated_global = self.upsert_workflow_definition_by_id(global_definitions, definition)
            self.set_custom_workflow_definitions(remaining_local)
            try:
                self.set_global_custom_workflow_definitions(updated_global)
            except OSError as exc:
                self.set_custom_workflow_definitions(local_definitions)
                return ControllerResult(
                    False,
                    f"Could not save global custom workflows.\n{exc}",
                    payload=False,
                )
            self._host.project_meta_changed.emit()
            self._host.node_library_changed.emit()
            return ControllerResult(True, payload=True)

        definition = find_custom_workflow_definition(global_definitions, normalized_workflow_id)
        if definition is None:
            return ControllerResult(False, "Global custom workflow not found.", payload=False)
        remaining_global = [
            item
            for item in global_definitions
            if str(item.get("workflow_id", "")).strip() != normalized_workflow_id
        ]
        updated_local = self.upsert_workflow_definition_by_id(local_definitions, definition)
        try:
            self.set_global_custom_workflow_definitions(remaining_global)
        except OSError as exc:
            return ControllerResult(
                False,
                f"Could not save global custom workflows.\n{exc}",
                payload=False,
            )
        self.set_custom_workflow_definitions(updated_local)
        self._host.project_meta_changed.emit()
        self._host.node_library_changed.emit()
        return ControllerResult(True, payload=True)

    def delete_custom_workflow(
        self,
        workflow_id: str,
        workflow_scope: str,
    ) -> ControllerResult[bool]:
        normalized_workflow_id = str(workflow_id or "").strip()
        normalized_scope = str(workflow_scope or "").strip().lower()
        if not normalized_workflow_id:
            return ControllerResult(False, "No custom workflow ID provided.", payload=False)
        if normalized_scope not in {_WORKFLOW_SCOPE_LOCAL, _WORKFLOW_SCOPE_GLOBAL}:
            return ControllerResult(False, "Custom workflow scope is invalid.", payload=False)

        if normalized_scope == _WORKFLOW_SCOPE_LOCAL:
            local_definitions = self.custom_workflow_definitions()
            remaining_local = [
                definition
                for definition in local_definitions
                if str(definition.get("workflow_id", "")).strip() != normalized_workflow_id
            ]
            if len(remaining_local) == len(local_definitions):
                return ControllerResult(False, "Project custom workflow not found.", payload=False)
            self.set_custom_workflow_definitions(remaining_local)
            self._host.project_meta_changed.emit()
            self._host.node_library_changed.emit()
            return ControllerResult(True, payload=True)

        global_definitions = self.global_custom_workflow_definitions()
        remaining_global = [
            definition
            for definition in global_definitions
            if str(definition.get("workflow_id", "")).strip() != normalized_workflow_id
        ]
        if len(remaining_global) == len(global_definitions):
            return ControllerResult(False, "Global custom workflow not found.", payload=False)
        try:
            self.set_global_custom_workflow_definitions(remaining_global)
        except OSError as exc:
            return ControllerResult(
                False,
                f"Could not save global custom workflows.\n{exc}",
                payload=False,
            )
        self._host.node_library_changed.emit()
        return ControllerResult(True, payload=True)

    def rename_custom_workflow(
        self,
        workflow_id: str,
        workflow_scope: str,
    ) -> ControllerResult[bool]:
        from PyQt6.QtWidgets import QInputDialog

        normalized_workflow_id = str(workflow_id or "").strip()
        normalized_scope = str(workflow_scope or "").strip().lower()
        if not normalized_workflow_id:
            return ControllerResult(False, "No custom workflow ID provided.", payload=False)
        if normalized_scope not in {_WORKFLOW_SCOPE_LOCAL, _WORKFLOW_SCOPE_GLOBAL}:
            return ControllerResult(False, "Custom workflow scope is invalid.", payload=False)

        if normalized_scope == _WORKFLOW_SCOPE_GLOBAL:
            current_definition = find_custom_workflow_definition(
                self.global_custom_workflow_definitions(),
                normalized_workflow_id,
            )
        else:
            current_definition = find_custom_workflow_definition(
                self.custom_workflow_definitions(),
                normalized_workflow_id,
            )

        if current_definition is None:
            return ControllerResult(False, "Custom workflow not found.", payload=False)

        current_name = str(current_definition.get("name", "")).strip()
        name, ok = QInputDialog.getText(resolve_dialog_parent(self._host), "Rename Workflow", "New name:", text=current_name)
        if not ok:
            return ControllerResult(False, payload=False)
        normalized_name = str(name or "").strip()
        if not normalized_name or normalized_name == current_name:
            return ControllerResult(False, payload=False)

        if normalized_scope == _WORKFLOW_SCOPE_GLOBAL:
            updated_global = self.rename_workflow_definition_by_id(
                self.global_custom_workflow_definitions(),
                normalized_workflow_id,
                normalized_name,
            )
            if updated_global is None:
                return ControllerResult(False, "Global custom workflow not found.", payload=False)
            try:
                self.set_global_custom_workflow_definitions(updated_global)
            except OSError as exc:
                return ControllerResult(
                    False,
                    f"Could not save global custom workflows.\n{exc}",
                    payload=False,
                )
            self._host.node_library_changed.emit()
            return ControllerResult(True, payload=True)

        updated_local = self.rename_workflow_definition_by_id(
            self.custom_workflow_definitions(),
            normalized_workflow_id,
            normalized_name,
        )
        if updated_local is None:
            return ControllerResult(False, "Project custom workflow not found.", payload=False)
        self.set_custom_workflow_definitions(updated_local)
        self._host.project_meta_changed.emit()
        self._host.node_library_changed.emit()
        return ControllerResult(True, payload=True)

    def publish_custom_workflow_from_selected_subnode(self) -> ControllerResult[bool]:
        selected = self._selection_context.selected_node_context()
        if selected is None:
            return ControllerResult(False, "Select a subnode shell to publish.", payload=False)
        node, _spec = selected
        if node.type_id != SUBNODE_TYPE_ID:
            return ControllerResult(False, "Selected node is not a subnode shell.", payload=False)
        return self.publish_custom_workflow_from_shell(node.node_id)

    def publish_custom_workflow_from_current_scope(self) -> ControllerResult[bool]:
        scope_shell_id = scope_parent_id(self._host.scene.active_scope_path)
        if not scope_shell_id:
            return ControllerResult(False, "Open a subnode scope to publish.", payload=False)
        return self.publish_custom_workflow_from_shell(scope_shell_id)

    def publish_custom_workflow_from_node(self, node_id: str) -> ControllerResult[bool]:
        normalized_node_id = str(node_id or "").strip()
        if not normalized_node_id:
            return ControllerResult(False, "No node ID provided.", payload=False)
        return self.publish_custom_workflow_from_shell(normalized_node_id)

    def publish_custom_workflow_from_shell(self, shell_node_id: str) -> ControllerResult[bool]:
        workspace = self._selection_context.active_workspace()
        if workspace is None:
            return ControllerResult(False, "Workspace not found.", payload=False)
        shell_node = workspace.nodes.get(str(shell_node_id).strip())
        if shell_node is None or shell_node.type_id != SUBNODE_TYPE_ID:
            return ControllerResult(False, "Subnode shell not found in workspace.", payload=False)

        snapshot = build_subnode_custom_workflow_snapshot_data(
            workspace=workspace,
            registry=self._host.registry,
            shell_node_id=shell_node.node_id,
        )
        if snapshot is None:
            return ControllerResult(False, "Could not build subnode snapshot.", payload=False)

        fragment = snapshot.get("fragment")
        if not isinstance(fragment, dict):
            return ControllerResult(False, "Subnode snapshot fragment is invalid.", payload=False)
        nodes_payload = fragment.get("nodes")
        edges_payload = fragment.get("edges")
        if not isinstance(nodes_payload, list) or not isinstance(edges_payload, list):
            return ControllerResult(False, "Subnode snapshot fragment is invalid.", payload=False)

        graph_fragment_payload = build_graph_fragment_payload(
            nodes=copy.deepcopy(nodes_payload),
            edges=copy.deepcopy(edges_payload),
        )
        normalized_fragment = normalize_graph_fragment_payload(graph_fragment_payload)
        if normalized_fragment is None:
            return ControllerResult(False, "Subnode snapshot fragment is invalid.", payload=False)

        try:
            updated_definitions, _saved_definition = upsert_custom_workflow_definition(
                self.custom_workflow_definitions(),
                workflow_id=_published_workflow_id(shell_node.node_id),
                name=shell_node.title,
                description=_CUSTOM_WORKFLOW_DESCRIPTION,
                ports=copy.deepcopy(snapshot.get("ports", [])),
                fragment=normalized_fragment,
            )
        except ValueError as exc:
            return ControllerResult(False, str(exc), payload=False)
        self.set_custom_workflow_definitions(updated_definitions)
        self._host.project_meta_changed.emit()
        self._host.node_library_changed.emit()
        return ControllerResult(True, payload=True)
