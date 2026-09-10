from __future__ import annotations

import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.ui.shell.controllers.mutation_ui_effects import MutationUiEffects
from ea_node_editor.ui.shell.controllers.project_session_controller import (
    _WorkspaceSessionAdapter,
)
from ea_node_editor.ui.shell.controllers.workflow_library_controller import (
    WorkflowLibraryController,
)
from ea_node_editor.ui.shell.controllers.workspace_drop_connect_controller import (
    WorkspaceDropConnectController,
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
from ea_node_editor.ui.shell.controllers.workspace_view_nav_ops import (
    WorkspaceViewNavOps,
)
from tests.workspace_controller_support import compose_workspace_controllers


class _SignalCounter:
    def __init__(self) -> None:
        self.calls = 0

    def emit(self) -> None:
        self.calls += 1


class _SearchScopeControllerStub:
    def __init__(self) -> None:
        self.restore_calls = 0
        self.discard_calls: list[tuple[str, str]] = []

    def restore_scope_camera(self) -> bool:
        self.restore_calls += 1
        return True

    def discard_scope_camera_for_view(self, workspace_id: str, view_id: str) -> None:
        self.discard_calls.append((workspace_id, view_id))


class _CloseViewWorkspace:
    def __init__(self) -> None:
        self.views = {"view-1": object(), "view-2": object()}
        self.active_view_id = "view-2"

    def ensure_default_view(self) -> None:
        return


class _CloseViewMutationService:
    def __init__(self, workspace: _CloseViewWorkspace) -> None:
        self._workspace = workspace
        self.active_view_state_calls = 0
        self.closed: list[str] = []

    def active_view_state(self) -> object:
        self.active_view_state_calls += 1
        self._workspace.ensure_default_view()
        return object()

    def close_view(self, view_id: str) -> None:
        self.closed.append(view_id)
        self._workspace.views.pop(view_id, None)
        if self._workspace.active_view_id == view_id and self._workspace.views:
            self._workspace.active_view_id = next(iter(self._workspace.views))


class _CloseViewModel:
    def __init__(self, workspace: _CloseViewWorkspace) -> None:
        self.project = SimpleNamespace(workspaces={"ws-1": workspace})
        self.workspace_view_mutation_calls: list[str] = []
        self.workspace_view_mutation_instance = _CloseViewMutationService(workspace)

    def workspace_view_mutations(self, workspace_id: str) -> _CloseViewMutationService:
        self.workspace_view_mutation_calls.append(workspace_id)
        return self.workspace_view_mutation_instance


class _CloseViewWorkspaceManager:
    def __init__(self) -> None:
        self.closed: list[tuple[str, str]] = []

    def active_workspace_id(self) -> str:
        return "ws-1"

    def close_view(self, workspace_id: str, view_id: str) -> None:
        self.closed.append((workspace_id, view_id))


class _CloseViewHostStub:
    def __init__(self) -> None:
        workspace = _CloseViewWorkspace()
        self.model = _CloseViewModel(workspace)
        self.workspace_manager = _CloseViewWorkspaceManager()
        self.sync_scope_calls = 0
        self.scene = SimpleNamespace(
            sync_scope_with_active_view=self._sync_scope_with_active_view
        )
        self.search_scope_controller = _SearchScopeControllerStub()
        self.workspace_state_changed = _SignalCounter()

    def _sync_scope_with_active_view(self) -> None:
        self.sync_scope_calls += 1


class _CreateWorkspaceManagerStub:
    def __init__(self) -> None:
        self.create_calls: list[str | None] = []

    def create_workspace(self, name: str | None = None) -> str:
        self.create_calls.append(name)
        return "ws-created"


class _RuntimeHistoryStub:
    def __init__(self) -> None:
        self.cleared: list[str] = []

    def clear_workspace(self, workspace_id: str) -> None:
        self.cleared.append(workspace_id)


class _CreateWorkspaceHostStub:
    def __init__(self) -> None:
        self.workspace_manager = _CreateWorkspaceManagerStub()
        self.runtime_history = _RuntimeHistoryStub()


class _ViewMutationWorkspaceManagerStub:
    def __init__(self, workspace_id: str) -> None:
        self._workspace_id = workspace_id

    def active_workspace_id(self) -> str:
        return self._workspace_id

    def set_active_workspace(self, workspace_id: str) -> None:
        self._workspace_id = workspace_id


class _ViewMutationControllerStub:
    def __init__(self) -> None:
        self.save_calls = 0
        self.restore_calls = 0
        self.refresh_calls = 0

    def save_active_view_state(self) -> None:
        self.save_calls += 1

    def restore_active_view_state(self) -> None:
        self.restore_calls += 1

    def refresh_workspace_tabs(self) -> None:
        self.refresh_calls += 1


class _WorkspaceSceneStub:
    def __init__(self) -> None:
        self.set_workspace_calls: list[str] = []

    def set_workspace(self, model, registry, workspace_id: str) -> None:  # noqa: ANN001
        self.set_workspace_calls.append(workspace_id)


class _ScriptEditorStub:
    def __init__(self) -> None:
        self.set_node_calls: list[object | None] = []

    def set_node(self, node: object | None) -> None:
        self.set_node_calls.append(node)


class _ViewMutationHostStub:
    def __init__(self) -> None:
        self.model = GraphModel()
        self.workspace_manager = _ViewMutationWorkspaceManagerStub(
            self.model.active_workspace.workspace_id
        )
        self.registry = object()
        self.scene = _WorkspaceSceneStub()
        self.script_editor = _ScriptEditorStub()
        self.workspace_state_changed = _SignalCounter()
        self.run_action_update_calls = 0
        self.run_projection_controller = SimpleNamespace(
            update_run_actions=self._update_run_actions
        )

    def _update_run_actions(self) -> None:
        self.run_action_update_calls += 1


class _PointStub:
    def __init__(self, x_value: float, y_value: float) -> None:
        self._x = x_value
        self._y = y_value

    def x(self) -> float:
        return self._x

    def y(self) -> float:
        return self._y


class _ViewportRectStub:
    def center(self) -> object:
        return object()


class _ViewportStub:
    def rect(self) -> _ViewportRectStub:
        return _ViewportRectStub()


class _ViewStub:
    def viewport(self) -> _ViewportStub:
        return _ViewportStub()

    def mapToScene(self, _point: object) -> _PointStub:
        return _PointStub(125.0, 220.0)


class _LibraryInsertHostStub:
    def __init__(self) -> None:
        self.view = _ViewStub()


class _DropConnectControllerStub:
    def __init__(self, workspace) -> None:  # noqa: ANN001
        self._workspace = workspace
        self.prompt_calls = 0

    def resolve_custom_workflow_definition(
        self, workflow_id: str
    ) -> dict[str, object] | None:  # noqa: ARG002
        return None

    def active_workspace(self):
        return self._workspace

    def prompt_connection_candidate(
        self,
        *,
        title: str,
        label: str,
        candidates: list[dict[str, object]],
    ) -> dict[str, object] | None:
        self.prompt_calls += 1
        return None

    def refresh_workspace_tabs(self) -> None:
        return


class _SelectingDropConnectControllerStub(_DropConnectControllerStub):
    def __init__(self, workspace) -> None:  # noqa: ANN001
        super().__init__(workspace)
        self.last_candidates: list[dict[str, object]] = []

    def prompt_connection_candidate(
        self,
        *,
        title: str,
        label: str,
        candidates: list[dict[str, object]],
    ) -> dict[str, object] | None:
        self.prompt_calls += 1
        self.last_candidates = list(candidates)
        return candidates[0] if candidates else None


def _drop_connect_owner(
    host: object,
    callbacks: _DropConnectControllerStub,
) -> WorkspaceDropConnectController:
    effects = MutationUiEffects(host=host, refresh_workspace_tabs=lambda: None)
    return WorkspaceDropConnectController(
        host,  # type: ignore[arg-type]
        active_workspace=callbacks.active_workspace,
        resolve_custom_workflow_definition=(
            callbacks.resolve_custom_workflow_definition
        ),
        prompt_connection_candidate=callbacks.prompt_connection_candidate,
        effects=effects,
    )


class _DropConnectSceneStub:
    def __init__(self, model: GraphModel, workspace_id: str, registry) -> None:  # noqa: ANN001
        self._model = model
        self._workspace_id = workspace_id
        self._registry = registry
        self.removed_edge_ids: list[str] = []
        self.added_edges: list[tuple[str, str, str, str, bool, int, bool]] = []

    def add_edge(
        self,
        source_node_id: str,
        source_port_key: str,
        target_node_id: str,
        target_port_key: str,
        append_requested: bool = False,
    ) -> str:
        edge = self._model.validated_mutations(
            workspace_id=self._workspace_id,
            registry=self._registry,
        ).add_edge(
            source_node_id=source_node_id,
            source_port_key=source_port_key,
            target_node_id=target_node_id,
            target_port_key=target_port_key,
            append_requested=bool(append_requested),
        )
        self.added_edges.append(
            (
                source_node_id,
                source_port_key,
                target_node_id,
                target_port_key,
                bool(append_requested),
                edge.input_order,
                edge.enabled,
            )
        )
        return edge.edge_id

    def remove_edge(self, edge_id: str) -> None:
        self._model.remove_edge(self._workspace_id, edge_id)
        self.removed_edge_ids.append(edge_id)


class _LibraryInsertionSceneStub:
    def __init__(self) -> None:
        self.active_scope_path: tuple[str, ...] = ()
        self.create_calls: list[dict[str, object]] = []
        self.create_result = "node-created"

    def create_node_from_type(
        self,
        *,
        type_id: str,
        x: float,
        y: float,
        parent_node_id: str | None,
        select_node: bool,
        property_overrides: dict[str, object] | None = None,
    ) -> str:
        self.create_calls.append(
            {
                "type_id": type_id,
                "x": x,
                "y": y,
                "parent_node_id": parent_node_id,
                "select_node": select_node,
                "property_overrides": dict(property_overrides or {}),
            }
        )
        return self.create_result


class _LibraryInsertionHostStub:
    def __init__(self) -> None:
        self.scene = _LibraryInsertionSceneStub()
        self.app_preferences_controller = SimpleNamespace(
            record_node_library_usage=self._record_usage
        )
        self.recorded_usage: list[str] = []

    def _record_usage(self, type_id: str) -> None:
        self.recorded_usage.append(type_id)


class _NavigationSurfaceStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def save_active_view_state(self) -> None:
        self.calls.append(("save", None))

    def refresh_workspace_tabs(self) -> None:
        self.calls.append(("refresh", None))

    def switch_workspace(self, workspace_id: str) -> None:
        self.calls.append(("switch", workspace_id))


class ProjectSessionWorkspaceSurfaceTests(unittest.TestCase):
    def test_project_session_adapter_requires_workspace_navigation_controller(
        self,
    ) -> None:
        adapter = _WorkspaceSessionAdapter(
            SimpleNamespace(workspace_library_controller=object())
        )

        with self.assertRaisesRegex(RuntimeError, "workspace surface"):
            adapter.save_active_view_state()

    def test_project_session_adapter_uses_workspace_navigation_controller_directly(
        self,
    ) -> None:
        navigation = _NavigationSurfaceStub()
        adapter = _WorkspaceSessionAdapter(
            SimpleNamespace(workspace_navigation_controller=navigation)
        )

        adapter.save_active_view_state()
        adapter.refresh_workspace_tabs()
        adapter.switch_workspace("ws-target")

        self.assertEqual(
            navigation.calls,
            [
                ("save", None),
                ("refresh", None),
                ("switch", "ws-target"),
            ],
        )


class WorkspaceDirectControllerCompositionTests(unittest.TestCase):
    def test_controller_initializes_focused_controller_owners_with_direct_surfaces(
        self,
    ) -> None:
        owners = compose_workspace_controllers(SimpleNamespace())

        self.assertIsInstance(owners.workflow, WorkflowLibraryController)
        self.assertIsInstance(owners.navigation, WorkspaceNavigationController)
        self.assertIsInstance(owners.drop, WorkspaceDropConnectController)
        self.assertIsInstance(owners.package, WorkspacePackageIOController)
        self.assertIs(owners.edit.mutation_ui_effects, owners.effects)
        self.assertIs(owners.drop.mutation_ui_effects, owners.effects)
        self.assertIs(owners.navigation._ops._controller, owners.navigation)
        self.assertIs(owners.package._ops._controller, owners.package)

    def test_selection_context_is_shared_by_direct_edit_and_workflow_owners(
        self,
    ) -> None:
        owners = compose_workspace_controllers(SimpleNamespace())

        self.assertIsInstance(owners.selection, WorkspaceSelectionContext)
        self.assertIs(owners.edit._selection_context, owners.selection)
        self.assertIs(owners.workflow._selection_context, owners.selection)

    def test_internal_capabilities_delegate_only_to_focused_subcontrollers(
        self,
    ) -> None:
        owners = compose_workspace_controllers(SimpleNamespace())

        self.assertFalse(hasattr(owners, "workspace_library_controller"))
        self.assertFalse(hasattr(owners, "workspace_graph_edit_controller"))
        self.assertIsNot(owners.edit, owners.drop)
        self.assertIs(owners.edit.mutation_ui_effects, owners.drop.mutation_ui_effects)


class WorkspaceDropConnectControllerCallbackTests(unittest.TestCase):
    def test_graph_edit_controller_uses_workflow_library_callback_surface(self) -> None:
        host = SimpleNamespace()
        callbacks = _DropConnectControllerStub(GraphModel().active_workspace)
        callbacks.resolve_custom_workflow_definition = lambda workflow_id: {
            "workflow_id": workflow_id
        }
        controller = _drop_connect_owner(host, callbacks)

        self.assertEqual(
            controller._resolve_custom_workflow_definition("wf-1"),
            {"workflow_id": "wf-1"},
        )


class WorkspaceEditControllerEffectsTests(unittest.TestCase):
    def test_graph_edit_controller_uses_navigation_refresh_callback_surface(
        self,
    ) -> None:
        owners = compose_workspace_controllers(SimpleNamespace())
        refresh_calls: list[str] = []
        owners.navigation.refresh_workspace_tabs = lambda: refresh_calls.append(
            "refresh"
        )

        owners.effects.refresh_workspace_tabs()

        self.assertEqual(refresh_calls, ["refresh"])


class WorkspacePackageIOControllerCallbackTests(unittest.TestCase):
    def test_package_io_controller_uses_workflow_library_definition_surfaces(
        self,
    ) -> None:
        recorded_definitions: list[list[dict[str, object]]] = []
        definitions = [{"workflow_id": "wf-1"}]
        controller = WorkspacePackageIOController(
            SimpleNamespace(),  # type: ignore[arg-type]
            lambda: list(definitions),
            lambda items: recorded_definitions.append(list(items)),
        )

        self.assertEqual(controller.custom_workflow_definitions(), definitions)

        updated = [{"workflow_id": "wf-2"}]
        controller.set_custom_workflow_definitions(updated)

        self.assertEqual(recorded_definitions, [updated])

    def test_prompt_custom_workflow_export_definition_returns_only_definition(
        self,
    ) -> None:
        controller = WorkspacePackageIOController(
            SimpleNamespace(),  # type: ignore[arg-type]
            lambda: [],
            lambda _items: None,
        )
        definition = {"workflow_id": "wf-1"}

        self.assertIs(
            controller.prompt_custom_workflow_export_definition([definition]),
            definition,
        )


class WorkspaceNavigationControllerCloseViewTests(unittest.TestCase):
    def test_close_view_uses_search_scope_controller_for_camera_state(self) -> None:
        host = _CloseViewHostStub()
        controller = WorkspaceNavigationController(host)  # type: ignore[arg-type]
        restore_calls: list[str] = []
        controller.restore_active_view_state = lambda: restore_calls.append("restore")  # type: ignore[method-assign]

        closed = controller.close_view("view-2")

        self.assertTrue(closed)
        self.assertEqual(host.workspace_manager.closed, [])
        self.assertEqual(host.model.workspace_view_mutation_calls, ["ws-1"])
        self.assertEqual(host.model.workspace_view_mutation_instance.closed, ["view-2"])
        self.assertEqual(
            host.model.workspace_view_mutation_instance.active_view_state_calls, 1
        )
        self.assertEqual(restore_calls, ["restore"])
        self.assertEqual(host.sync_scope_calls, 1)
        self.assertEqual(host.search_scope_controller.restore_calls, 1)
        self.assertEqual(
            host.search_scope_controller.discard_calls, [("ws-1", "view-2")]
        )
        self.assertEqual(host.workspace_state_changed.calls, 1)


class WorkspaceDropConnectControllerInsertionTests(unittest.TestCase):
    def test_library_insert_records_successful_explicit_choice(self) -> None:
        recorded_usage: list[str] = []
        host = SimpleNamespace(
            scene=_LibraryInsertionSceneStub(),
            app_preferences_controller=SimpleNamespace(
                record_node_library_usage=recorded_usage.append
            ),
        )
        controller = _DropConnectControllerStub(GraphModel().active_workspace)
        ops = _drop_connect_owner(host, controller)

        node_id = ops.insert_library_node("core.python_script", 12.0, 34.0)

        self.assertEqual(node_id, "node-created")
        [create_call] = host.scene.create_calls
        self.assertEqual(create_call["type_id"], "core.python_script")
        self.assertEqual(create_call["x"], 12.0)
        self.assertEqual(create_call["y"], 34.0)
        self.assertIsNone(create_call["parent_node_id"])
        self.assertFalse(create_call["select_node"])
        self.assertEqual(recorded_usage, ["core.python_script"])

    def test_failed_library_insert_does_not_record_usage(self) -> None:
        recorded_usage: list[str] = []
        host = SimpleNamespace(
            scene=_LibraryInsertionSceneStub(),
            app_preferences_controller=SimpleNamespace(
                record_node_library_usage=recorded_usage.append
            ),
        )
        host.scene.create_result = ""
        controller = _DropConnectControllerStub(GraphModel().active_workspace)
        ops = _drop_connect_owner(host, controller)

        self.assertEqual(ops.insert_library_node("core.logger", 12.0, 34.0), "")
        self.assertEqual(recorded_usage, [])

    def test_library_insert_with_properties_is_unselected(self) -> None:
        host = _LibraryInsertionHostStub()
        controller = _DropConnectControllerStub(GraphModel().active_workspace)
        ops = _drop_connect_owner(host, controller)

        node_id = ops.insert_library_node_with_properties(
            "core.logger",
            {"level": "warning"},
            12.0,
            34.0,
        )

        self.assertEqual(node_id, "node-created")
        [create_call] = host.scene.create_calls
        self.assertFalse(create_call["select_node"])
        self.assertEqual(create_call["property_overrides"], {"level": "warning"})


class WorkspaceNavigationControllerCreationTests(unittest.TestCase):
    def test_create_workspace_uses_controller_refresh_and_switch_hooks(self) -> None:
        from unittest.mock import patch

        host = _CreateWorkspaceHostStub()
        controller = WorkspaceNavigationController(host)  # type: ignore[arg-type]
        refresh_calls: list[str] = []
        switch_calls: list[str] = []
        controller.refresh_workspace_tabs = lambda: refresh_calls.append("refresh")  # type: ignore[method-assign]
        controller.switch_workspace = lambda workspace_id: switch_calls.append(
            workspace_id
        )  # type: ignore[method-assign]

        with patch(
            "PyQt6.QtWidgets.QInputDialog.getText",
            return_value=("Refactor Scope", True),
        ):
            controller.create_workspace()

        self.assertEqual(host.workspace_manager.create_calls, ["Refactor Scope"])
        self.assertEqual(host.runtime_history.cleared, ["ws-created"])
        self.assertEqual(refresh_calls, ["refresh"])
        self.assertEqual(switch_calls, ["ws-created"])


class WorkspaceDropConnectControllerViewportTests(unittest.TestCase):
    def test_add_node_from_library_does_not_refresh_workspace_tabs(self) -> None:
        host = _LibraryInsertHostStub()
        callbacks = _DropConnectControllerStub(GraphModel().active_workspace)
        controller = _drop_connect_owner(host, callbacks)
        insert_calls: list[tuple[str, float, float]] = []
        refresh_calls: list[str] = []

        def _insert(type_id: str, x_value: float, y_value: float) -> str:
            insert_calls.append((type_id, x_value, y_value))
            return "node-1"

        controller.insert_library_node = _insert  # type: ignore[method-assign]

        controller.add_node_from_library("core.logger")

        self.assertEqual(insert_calls, [("core.logger", 125.0, 220.0)])
        self.assertEqual(refresh_calls, [])


class WorkspaceViewNavOpsMutationServiceTests(unittest.TestCase):
    def test_create_view_uses_model_view_mutation_without_workspace_manager_view_helpers(
        self,
    ) -> None:
        from unittest.mock import patch

        host = _ViewMutationHostStub()
        controller = _ViewMutationControllerStub()
        ops = WorkspaceViewNavOps(host, controller)  # type: ignore[arg-type]

        with patch(
            "PyQt6.QtWidgets.QInputDialog.getText", return_value=("Review", True)
        ):
            ops.create_view()

        workspace = host.model.active_workspace
        self.assertEqual(controller.save_calls, 1)
        self.assertEqual(controller.restore_calls, 1)
        self.assertEqual(host.workspace_state_changed.calls, 1)
        self.assertEqual(len(workspace.views), 2)
        self.assertEqual(workspace.views[workspace.active_view_id].name, "Review")

    def test_switch_view_uses_model_view_mutation_without_workspace_manager_view_helpers(
        self,
    ) -> None:
        host = _ViewMutationHostStub()
        workspace = host.model.active_workspace
        alternate_view = host.model.workspace_view_mutations(
            workspace.workspace_id
        ).create_view(name="Alt")
        controller = _ViewMutationControllerStub()
        ops = WorkspaceViewNavOps(host, controller)  # type: ignore[arg-type]

        ops.switch_view(alternate_view.view_id)

        self.assertEqual(controller.save_calls, 1)
        self.assertEqual(controller.restore_calls, 1)
        self.assertEqual(host.workspace_state_changed.calls, 1)
        self.assertEqual(workspace.active_view_id, alternate_view.view_id)

    def test_switch_workspace_refreshes_run_controls_immediately(self) -> None:
        host = _ViewMutationHostStub()
        source_workspace_id = host.workspace_manager.active_workspace_id()
        target_workspace = host.model.create_workspace(name="Review Target")
        host.workspace_manager.set_active_workspace(source_workspace_id)
        controller = _ViewMutationControllerStub()
        ops = WorkspaceViewNavOps(host, controller)  # type: ignore[arg-type]

        ops.switch_workspace(target_workspace.workspace_id)

        self.assertEqual(controller.save_calls, 1)
        self.assertEqual(controller.restore_calls, 1)
        self.assertEqual(controller.refresh_calls, 1)
        self.assertEqual(
            host.workspace_manager.active_workspace_id(), target_workspace.workspace_id
        )
        self.assertEqual(
            host.scene.set_workspace_calls, [target_workspace.workspace_id]
        )
        self.assertEqual(host.script_editor.set_node_calls, [None])
        self.assertEqual(host.run_action_update_calls, 1)
        self.assertEqual(host.workspace_state_changed.calls, 1)


class WorkspaceDropConnectControllerValidationTests(unittest.TestCase):
    def test_quick_insert_port_keys_restrict_actual_ports_and_keep_none_unrestricted(self) -> None:
        registry = build_default_registry()
        for keys, expected_keys in ((None, ["value", "as_text"]), (("as_text",), ["as_text"]), ((), []), (("stale",), [])):
            with self.subTest(keys=keys):
                model = GraphModel()
                workspace = model.active_workspace
                source = model.add_node(workspace.workspace_id, "core.constant", "New", 0.0, 0.0)
                target = model.add_node(workspace.workspace_id, "core.if", "Target", 300.0, 0.0)
                callbacks = _SelectingDropConnectControllerStub(workspace)
                ops = _drop_connect_owner(SimpleNamespace(registry=registry, scene=_DropConnectSceneStub(model, workspace.workspace_id, registry)), callbacks)
                connected = ops.auto_connect_dropped_node_to_port(source.node_id, target.node_id, "true_value", compatible_port_keys=keys)
                self.assertEqual([item["source_port_key"] for item in callbacks.last_candidates], expected_keys)
                self.assertEqual(connected, bool(expected_keys))
                self.assertEqual(len(workspace.edges), int(bool(expected_keys)))

    def test_quick_insert_rechecks_selected_type_and_resolves_default_dynamic_ports(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        source = model.add_node(workspace.workspace_id, "core.constant", "New", 0.0, 0.0)
        path_target = model.add_node(workspace.workspace_id, "io.file_read", "Path", 300.0, 0.0)
        callbacks = _SelectingDropConnectControllerStub(workspace)
        ops = _drop_connect_owner(SimpleNamespace(registry=registry, scene=_DropConnectSceneStub(model, workspace.workspace_id, registry)), callbacks)
        self.assertFalse(ops.auto_connect_dropped_node_to_port(source.node_id, path_target.node_id, "path", compatible_port_keys=("value",)))
        self.assertEqual(workspace.edges, {})
        dynamic = model.add_node(workspace.workspace_id, "core.stream_gate", "Dynamic", 0.0, 100.0)
        target = model.add_node(workspace.workspace_id, "core.if", "Target", 300.0, 100.0)
        self.assertTrue(ops.auto_connect_dropped_node_to_port(dynamic.node_id, target.node_id, "true_value", compatible_port_keys=("output_1",)))
        self.assertEqual(next(iter(workspace.edges.values())).source_port_key, "output_1")

    def test_workflow_restrictions_use_preview_keys_and_recheck_live_endpoint_types(self) -> None:
        registry = build_default_registry()
        for keys, expected in ((None, "value"), (("preview_text",), "as_text"), (("as_text",), None), ((), None), (("stale",), None)):
            with self.subTest(keys=keys):
                model = GraphModel()
                workspace = model.active_workspace
                source = model.add_node(workspace.workspace_id, "core.constant", "New", 0.0, 0.0)
                target = model.add_node(workspace.workspace_id, "core.if", "Target", 300.0, 0.0)
                callbacks = _SelectingDropConnectControllerStub(workspace)
                ops = _drop_connect_owner(SimpleNamespace(registry=registry, scene=_DropConnectSceneStub(model, workspace.workspace_id, registry)), callbacks)
                endpoints = [{"key": "preview_value", "node_id": source.node_id, "port_key": "value"}, {"key": "preview_text", "node_id": source.node_id, "port_key": "as_text"}]
                connected = ops._connect_workflow_endpoint_to_port(endpoints, target.node_id, "true_value", compatible_port_keys=keys)
                self.assertEqual(connected, expected is not None)
                if expected is not None:
                    self.assertEqual(next(iter(workspace.edges.values())).source_port_key, expected)
                else:
                    self.assertEqual(workspace.edges, {})
                path_target = model.add_node(workspace.workspace_id, "io.file_read", "Path", 500.0, 0.0)
                self.assertFalse(ops._connect_workflow_endpoint_to_port(endpoints, path_target.node_id, "path", compatible_port_keys=("preview_value",)))

    def test_restricted_workflow_drop_with_stale_endpoints_never_falls_back_to_shell(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        host = SimpleNamespace(runtime_history=SimpleNamespace(grouped_action=lambda *_args: nullcontext()))
        ops = _drop_connect_owner(host, _DropConnectControllerStub(workspace))
        with (
            patch.object(ops, "insert_custom_workflow_snapshot_with_endpoints", return_value=("created", [])),
            patch.object(ops, "insert_library_node", return_value="created"),
            patch.object(ops, "_connect_workflow_endpoint_to_port", return_value=False) as workflow_connect,
            patch.object(ops, "auto_connect_dropped_node_to_port", return_value=False) as node_connect,
        ):
            result = ops.request_drop_node_from_library("custom_workflow:test", 0.0, 0.0, "port", "target", "input", "", compatible_port_keys=())
            self.assertTrue(result.payload)
            workflow_connect.assert_called_once_with([], "target", "input", False, compatible_port_keys=())
            node_connect.assert_not_called()
            ops.request_drop_node_from_library("core.constant", 0.0, 0.0, "port", "target", "input", "", compatible_port_keys=("as_text",))
            node_connect.assert_called_once_with("created", "target", "input", False, compatible_port_keys=("as_text",))

    def test_auto_connect_dropped_node_to_port_replaces_occupied_data_input(
        self,
    ) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        occupied_source = model.add_node(
            workspace.workspace_id, "core.trigger", "Trigger A", 0.0, 0.0
        )
        new_node = model.add_node(
            workspace.workspace_id, "core.trigger", "Trigger B", 0.0, 120.0
        )
        target = model.add_node(workspace.workspace_id, "core.if", "If", 320.0, 40.0)
        original = model.validated_mutations(
            workspace_id=workspace.workspace_id,
            registry=registry,
        ).add_edge(
            source_node_id=occupied_source.node_id,
            source_port_key="output",
            target_node_id=target.node_id,
            target_port_key="true_value",
        )

        scene = _DropConnectSceneStub(model, workspace.workspace_id, registry)
        host = SimpleNamespace(registry=registry, scene=scene)
        controller = _SelectingDropConnectControllerStub(workspace)
        ops = _drop_connect_owner(host, controller)

        connected = ops.auto_connect_dropped_node_to_port(
            new_node.node_id, target.node_id, "true_value"
        )

        self.assertTrue(connected)
        self.assertEqual(controller.prompt_calls, 1)
        self.assertNotIn(original.edge_id, workspace.edges)
        replacement = next(iter(workspace.edges.values()))
        self.assertEqual(replacement.source_node_id, new_node.node_id)
        self.assertEqual(replacement.target_port_key, "true_value")
        self.assertEqual(replacement.input_order, 0)
        self.assertTrue(replacement.enabled)

    def test_auto_connect_dropped_flowchart_node_to_neutral_port_keeps_existing_port_as_source(
        self,
    ) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        workspace_id = workspace.workspace_id
        target = model.add_node(
            workspace_id, "passive.flowchart.process", "Existing", 120.0, 120.0
        )
        new_node = model.add_node(
            workspace_id, "passive.flowchart.process", "Inserted", 420.0, 120.0
        )

        scene = _DropConnectSceneStub(model, workspace_id, registry)
        host = SimpleNamespace(registry=registry, scene=scene)
        controller = _SelectingDropConnectControllerStub(workspace)
        ops = _drop_connect_owner(host, controller)

        connected = ops.auto_connect_dropped_node_to_port(
            new_node.node_id, target.node_id, "right"
        )

        self.assertTrue(connected)
        self.assertEqual(controller.prompt_calls, 1)
        self.assertEqual(
            controller.last_candidates,
            [
                {
                    "source_node_id": target.node_id,
                    "source_port_key": "right",
                    "target_node_id": new_node.node_id,
                    "target_port_key": "left",
                    "label": "Process.right -> Process.left",
                }
            ],
        )
        edge = next(iter(workspace.edges.values()))
        self.assertEqual(edge.source_node_id, target.node_id)
        self.assertEqual(edge.source_port_key, "right")
        self.assertEqual(edge.target_node_id, new_node.node_id)
        self.assertEqual(edge.target_port_key, "left")
        self.assertEqual(
            scene.added_edges,
            [(target.node_id, "right", new_node.node_id, "left", False, 0, True)],
        )

    def test_auto_connect_dropped_passive_node_to_neutral_port_keeps_existing_port_as_source(
        self,
    ) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        workspace_id = workspace.workspace_id
        target = model.add_node(
            workspace_id, "passive.planning.task_card", "Existing", 120.0, 120.0
        )
        new_node = model.add_node(
            workspace_id, "passive.media.mail_panel", "Inserted", 420.0, 120.0
        )

        scene = _DropConnectSceneStub(model, workspace_id, registry)
        host = SimpleNamespace(registry=registry, scene=scene)
        controller = _SelectingDropConnectControllerStub(workspace)
        ops = _drop_connect_owner(host, controller)

        connected = ops.auto_connect_dropped_node_to_port(
            new_node.node_id, target.node_id, "right"
        )

        self.assertTrue(connected)
        self.assertEqual(controller.prompt_calls, 1)
        self.assertEqual(
            controller.last_candidates,
            [
                {
                    "source_node_id": target.node_id,
                    "source_port_key": "right",
                    "target_node_id": new_node.node_id,
                    "target_port_key": "left",
                    "label": "Task Card.right -> Mail Panel.left",
                }
            ],
        )
        edge = next(iter(workspace.edges.values()))
        self.assertEqual(edge.source_node_id, target.node_id)
        self.assertEqual(edge.source_port_key, "right")
        self.assertEqual(edge.target_node_id, new_node.node_id)
        self.assertEqual(edge.target_port_key, "left")

    def test_auto_connect_dropped_flowchart_node_to_neutral_edge_uses_distinct_facing_sides(
        self,
    ) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        workspace_id = workspace.workspace_id
        source = model.add_node(
            workspace_id, "passive.flowchart.process", "Source", 40.0, 100.0
        )
        target = model.add_node(
            workspace_id, "passive.flowchart.process", "Target", 640.0, 100.0
        )
        new_node = model.add_node(
            workspace_id, "passive.flowchart.process", "Inserted", 340.0, 100.0
        )
        original_edge = model.add_edge(
            workspace_id, source.node_id, "right", target.node_id, "left"
        )

        scene = _DropConnectSceneStub(model, workspace_id, registry)
        host = SimpleNamespace(registry=registry, scene=scene)
        controller = _SelectingDropConnectControllerStub(workspace)
        ops = _drop_connect_owner(host, controller)

        connected = ops.auto_connect_dropped_node_to_edge(
            new_node.node_id, original_edge.edge_id
        )

        self.assertTrue(connected)
        self.assertEqual(controller.prompt_calls, 1)
        self.assertEqual(
            controller.last_candidates,
            [
                {
                    "new_input_port": "left",
                    "new_output_port": "right",
                    "label": "Process.right -> Process.left, Process.right -> Process.left",
                }
            ],
        )
        self.assertEqual(scene.removed_edge_ids, [original_edge.edge_id])
        edge_tuples = {
            (
                edge.source_node_id,
                edge.source_port_key,
                edge.target_node_id,
                edge.target_port_key,
            )
            for edge in workspace.edges.values()
        }
        self.assertEqual(
            edge_tuples,
            {
                (source.node_id, "right", new_node.node_id, "left"),
                (new_node.node_id, "right", target.node_id, "left"),
            },
        )

    def test_auto_connect_dropped_passive_node_to_neutral_edge_uses_distinct_facing_sides(
        self,
    ) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        workspace_id = workspace.workspace_id
        source = model.add_node(
            workspace_id, "passive.annotation.sticky_note", "Source", 40.0, 100.0
        )
        target = model.add_node(
            workspace_id, "passive.media.mail_panel", "Target", 640.0, 100.0
        )
        new_node = model.add_node(
            workspace_id, "passive.planning.task_card", "Inserted", 340.0, 100.0
        )
        original_edge = model.add_edge(
            workspace_id, source.node_id, "right", target.node_id, "left"
        )

        scene = _DropConnectSceneStub(model, workspace_id, registry)
        host = SimpleNamespace(registry=registry, scene=scene)
        controller = _SelectingDropConnectControllerStub(workspace)
        ops = _drop_connect_owner(host, controller)

        connected = ops.auto_connect_dropped_node_to_edge(
            new_node.node_id, original_edge.edge_id
        )

        self.assertTrue(connected)
        self.assertEqual(controller.prompt_calls, 1)
        self.assertEqual(
            controller.last_candidates,
            [
                {
                    "new_input_port": "left",
                    "new_output_port": "right",
                    "label": "Sticky Note.right -> Task Card.left, Task Card.right -> Mail Panel.left",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
