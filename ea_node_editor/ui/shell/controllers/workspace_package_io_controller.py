# Purpose: Own custom-workflow and node-package import/export commands.
# Map: feature_routes/workflow_library_drop_connect
# Tests: tests/test_workspace_package_io_controller.py
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from ea_node_editor.ui.shell.controllers.workspace_io_ops import WorkspaceIOOps

if TYPE_CHECKING:
    from ea_node_editor.ui.shell.window import ShellWindow


class WorkspacePackageIOController:
    def __init__(
        self,
        host: ShellWindow,
        custom_workflow_definitions: Callable[[], list[dict[str, Any]]],
        set_custom_workflow_definitions: Callable[[list[dict[str, Any]]], None],
    ) -> None:
        self._custom_workflow_definitions = custom_workflow_definitions
        self._set_custom_workflow_definitions = set_custom_workflow_definitions
        self._ops = WorkspaceIOOps(host, self)

    def custom_workflow_definitions(self) -> list[dict[str, Any]]:
        return self._custom_workflow_definitions()

    def set_custom_workflow_definitions(self, definitions: list[dict[str, Any]]) -> None:
        self._set_custom_workflow_definitions(definitions)

    def prompt_custom_workflow_export_definition(
        self,
        definitions: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        return self._ops.prompt_custom_workflow_export_definition(definitions)

    @staticmethod
    def custom_workflow_export_label(definition: dict[str, Any]) -> str:
        return WorkspaceIOOps.custom_workflow_export_label(definition)

    @staticmethod
    def custom_workflow_default_filename(name: object) -> str:
        return WorkspaceIOOps.custom_workflow_default_filename(name)

    def import_custom_workflow(self) -> None:
        self._ops.import_custom_workflow()

    def export_custom_workflow(self) -> None:
        self._ops.export_custom_workflow()

    def import_node_package(self) -> None:
        self._ops.import_node_package()

    def export_node_package(self) -> None:
        self._ops.export_node_package()
