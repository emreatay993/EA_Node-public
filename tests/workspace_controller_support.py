from __future__ import annotations

from contextlib import nullcontext
from functools import partial
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ea_node_editor.custom_workflows import (
    export_custom_workflow_file,
    import_custom_workflow_file,
)
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.ui.graph_interactions import GraphActionResult
from ea_node_editor.ui.shell.controllers.result import ControllerResult
from ea_node_editor.ui.shell.controllers.mutation_ui_effects import MutationUiEffects
from ea_node_editor.ui.shell.controllers.workflow_library_controller import (
    WorkflowLibraryController,
)
from ea_node_editor.ui.shell.controllers.workspace_drop_connect_controller import (
    WorkspaceDropConnectController,
)
from ea_node_editor.ui.shell.controllers.workspace_edit_controller import (
    WorkspaceEditController,
)
from ea_node_editor.ui.shell.controllers.workspace_navigation_controller import (
    WorkspaceNavigationController,
)
from ea_node_editor.ui.shell.controllers.workspace_package_io_controller import (
    WorkspacePackageIOController,
)
from ea_node_editor.ui.shell.controllers.workspace_selection_context import (
    WorkspaceSelectionContext,
)
from ea_node_editor.ui.shell.library_flow import pick_connection_candidate


class _GraphInteractionsStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, str, bool]] = []

    def connect_ports(
        self,
        node_a_id: str,
        port_a: str,
        node_b_id: str,
        port_b: str,
        append_requested: bool = False,
    ) -> GraphActionResult:
        self.calls.append(
            (node_a_id, port_a, node_b_id, port_b, bool(append_requested))
        )
        return GraphActionResult(True, "")


class _WorkspaceHostStub:
    def __init__(self) -> None:
        self._graph_interactions = _GraphInteractionsStub()


class _WorkspaceManagerStub:
    def __init__(self, workspace_id: str) -> None:
        self._workspace_id = workspace_id

    def active_workspace_id(self) -> str:
        return self._workspace_id


class _RuntimeHistoryStub:
    def __init__(self) -> None:
        self.undo_return: object | None = object()
        self.redo_return: object | None = object()
        self.undo_calls: list[str] = []
        self.redo_calls: list[str] = []

    def undo_workspace(self, workspace_id: str, workspace: object) -> object | None:  # noqa: ARG002
        self.undo_calls.append(workspace_id)
        return self.undo_return

    def redo_workspace(self, workspace_id: str, workspace: object) -> object | None:  # noqa: ARG002
        self.redo_calls.append(workspace_id)
        return self.redo_return

    def grouped_action(self, workspace_id: str, action_type: str, workspace: object):  # noqa: ARG002
        return nullcontext()


class _SceneStub:
    def __init__(self) -> None:
        self.refreshed_workspaces: list[str] = []

    def refresh_workspace_from_model(self, workspace_id: str) -> None:
        self.refreshed_workspaces.append(workspace_id)


class _UndoRedoHostStub:
    def __init__(self) -> None:
        self._graph_interactions = _GraphInteractionsStub()
        self.model = GraphModel()
        self.runtime_history = _RuntimeHistoryStub()
        workspace_id = self.model.active_workspace.workspace_id
        self.workspace_manager = _WorkspaceManagerStub(workspace_id)
        self.scene = _SceneStub()


class _PointStub:
    def __init__(self, x: float, y: float) -> None:
        self._x = x
        self._y = y

    def x(self) -> float:
        return self._x

    def y(self) -> float:
        return self._y


class _RectStub:
    def center(self) -> _PointStub:
        return _PointStub(5.0, 9.0)


class _ViewportStub:
    def rect(self) -> _RectStub:
        return _RectStub()


class _ViewStub:
    def viewport(self) -> _ViewportStub:
        return _ViewportStub()

    def mapToScene(self, point: object) -> _PointStub:  # noqa: ARG002
        return _PointStub(120.0, 340.0)


class _ClipboardSceneStub:
    def __init__(self) -> None:
        self.fragment_payload: dict[str, object] | None = None
        self.paste_calls: list[tuple[dict[str, object], float, float]] = []
        self._fragment_center: tuple[float, float] = (100.0, 200.0)
        self.active_scope_path: list[str] = []

    def serialize_selected_subgraph_fragment(self) -> dict[str, object] | None:
        return self.fragment_payload

    def fragment_bounds_center(
        self, fragment_payload: object
    ) -> tuple[float, float] | None:  # noqa: ARG002
        return self._fragment_center

    def paste_subgraph_fragment(
        self, payload: dict[str, object], center_x: float, center_y: float
    ) -> bool:
        self.paste_calls.append((payload, center_x, center_y))
        return True


class _SignalStub:
    def __init__(self) -> None:
        self.calls = 0

    def emit(self) -> None:
        self.calls += 1


class _ClipboardHostStub:
    def __init__(self) -> None:
        self._graph_interactions = _GraphInteractionsStub()
        self.scene = _ClipboardSceneStub()
        self.view = _ViewStub()
        self.selected_node_changed = _SignalStub()


class _ScopeFocusSceneStub:
    def __init__(self) -> None:
        self.open_scope_calls: list[str] = []
        self.focus_calls: list[str] = []
        self.focus_results: dict[str, _PointStub | None] = {}

    def open_scope_for_node(self, node_id: str) -> bool:
        self.open_scope_calls.append(node_id)
        return True

    def focus_node(self, node_id: str):
        self.focus_calls.append(node_id)
        return self.focus_results.get(node_id, _PointStub(1.0, 2.0))


class _ScopeFocusHostStub:
    def __init__(self) -> None:
        self._graph_interactions = _GraphInteractionsStub()
        self.model = GraphModel()
        workspace_id = self.model.active_workspace.workspace_id
        self.workspace_manager = _WorkspaceManagerStub(workspace_id)
        self.scene = _ScopeFocusSceneStub()
        self.run_failure_focus_calls: list[tuple[str, str, str]] = []
        self.graph_hints: list[tuple[str, int]] = []
        self.run_projection_controller = self

    def set_run_failure_focus(
        self, workspace_id: str, node_id: str, *, node_title: str = ""
    ) -> None:
        self.run_failure_focus_calls.append((workspace_id, node_id, node_title))

    def show_graph_hint(self, message: str, timeout_ms: int) -> None:
        self.graph_hints.append((message, timeout_ms))


class _PinPropertySceneStub:
    def __init__(self) -> None:
        self.property_calls: list[tuple[str, str, object]] = []
        self.refreshed_workspaces: list[str] = []

    def set_node_property(self, node_id: str, key: str, value: object) -> None:
        self.property_calls.append((node_id, key, value))

    def set_port_label(
        self, workspace_id: str, node_id: str, port_key: str, label: str
    ) -> None:
        self.property_calls.append((node_id, port_key, label))

    def refresh_workspace_from_model(self, workspace_id: str) -> None:
        self.refreshed_workspaces.append(workspace_id)


class _ScriptEditorStub:
    def __init__(self) -> None:
        self.current_node_id = ""

    def set_node(self, _node: object) -> None:
        return


class _PinPropertyHostStub:
    def __init__(self) -> None:
        self._graph_interactions = _GraphInteractionsStub()
        self.model = GraphModel()
        workspace_id = self.model.active_workspace.workspace_id
        self.workspace_manager = _WorkspaceManagerStub(workspace_id)
        self.scene = _PinPropertySceneStub()
        self.script_editor = _ScriptEditorStub()
        self.selected_node_changed = _SignalStub()


class _PublishSceneStub:
    def __init__(self) -> None:
        self._selected_node_id = ""
        self.active_scope_path: list[str] = []

    def selected_node_id(self) -> str:
        return self._selected_node_id


class _PublishHostStub:
    def __init__(self) -> None:
        self._graph_interactions = _GraphInteractionsStub()
        self.model = GraphModel()
        self.registry = build_default_registry()
        workspace_id = self.model.active_workspace.workspace_id
        self.workspace_manager = _WorkspaceManagerStub(workspace_id)
        self.active_workspace_id = workspace_id
        self.scene = _PublishSceneStub()
        self.node_library_changed = _SignalStub()
        self.project_meta_changed = _SignalStub()


class WorkspaceDirectControllerTestBase(unittest.TestCase):
    @staticmethod
    def _valid_fragment_payload() -> dict[str, object]:
        return {
            "kind": "ea-node-editor/graph-fragment",
            "version": 2,
            "nodes": [
                {
                    "ref_id": "node_a",
                    "type_id": "core.constant",
                    "title": "Constant",
                    "x": 10.0,
                    "y": 20.0,
                    "collapsed": False,
                    "properties": {"value": 1},
                    "exposed_ports": {},
                    "parent_node_id": None,
                }
            ],
            "edges": [],
        }


def compose_workspace_controllers(host):  # noqa: ANN001, ANN201
    selection = WorkspaceSelectionContext(host)
    workflow = WorkflowLibraryController(host, selection)
    navigation = WorkspaceNavigationController(host)
    effects = MutationUiEffects(
        host=host,
        refresh_workspace_tabs=lambda: navigation.refresh_workspace_tabs(),
    )
    edit = WorkspaceEditController(
        host,
        selection_context=selection,
        effects=effects,
    )
    drop = WorkspaceDropConnectController(
        host,
        active_workspace=selection.active_workspace,
        resolve_custom_workflow_definition=workflow.resolve_custom_workflow_definition,
        prompt_connection_candidate=partial(
            pick_connection_candidate,
            parent=host,
        ),
        effects=effects,
    )
    package = WorkspacePackageIOController(
        host,
        workflow.custom_workflow_definitions,
        workflow.set_custom_workflow_definitions,
    )
    return SimpleNamespace(
        selection=selection,
        workflow=workflow,
        navigation=navigation,
        effects=effects,
        edit=edit,
        drop=drop,
        package=package,
    )


__all__ = [
    "ControllerResult",
    "GraphActionResult",
    "GraphModel",
    "Path",
    "MutationUiEffects",
    "WorkflowLibraryController",
    "WorkspaceDirectControllerTestBase",
    "WorkspaceDropConnectController",
    "WorkspaceEditController",
    "WorkspaceNavigationController",
    "WorkspacePackageIOController",
    "WorkspaceSelectionContext",
    "build_default_registry",
    "compose_workspace_controllers",
    "export_custom_workflow_file",
    "import_custom_workflow_file",
    "patch",
    "tempfile",
    "_ClipboardHostStub",
    "_GraphInteractionsStub",
    "_PinPropertyHostStub",
    "_PointStub",
    "_PublishHostStub",
    "_ScopeFocusHostStub",
    "_UndoRedoHostStub",
    "_WorkspaceHostStub",
    "_WorkspaceManagerStub",
]
