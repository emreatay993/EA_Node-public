from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
import unittest

from PyQt6.QtCore import QObject, pyqtSignal

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.builtins.media_panel import MEDIA_PANEL_TYPE_ID
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.ui.shell.controllers.workspace_drop_connect_controller import (
    WorkspaceDropConnectController,
)
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge


class _PreferenceSource(QObject):
    graphics_preferences_changed = pyqtSignal()

    def __init__(
        self,
        source_input_exposed: bool,
        *,
        show_title: bool = True,
        show_frame: bool = True,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.source_input_exposed = bool(source_input_exposed)
        self.show_title = bool(show_title)
        self.show_frame = bool(show_frame)

    @property
    def graphics_media_panel_defaults(self) -> dict[str, bool]:
        return {
            "show_title": self.show_title,
            "show_frame": self.show_frame,
            "autoplay_animations": True,
            "source_input_exposed": self.source_input_exposed,
        }

    @property
    def graphics_show_port_labels(self) -> bool:
        return True


class _SceneHost(QObject):
    def __init__(
        self,
        source_input_exposed: bool,
        *,
        show_title: bool = True,
        show_frame: bool = True,
    ) -> None:
        super().__init__()
        self.shell_workspace_presenter = _PreferenceSource(
            source_input_exposed,
            show_title=show_title,
            show_frame=show_frame,
            parent=self,
        )


def _bound_scene(
    source_input_exposed: bool,
    *,
    show_title: bool = True,
    show_frame: bool = True,
) -> tuple[GraphModel, GraphSceneBridge, _SceneHost]:
    registry = build_default_registry()
    model = GraphModel()
    host = _SceneHost(
        source_input_exposed,
        show_title=show_title,
        show_frame=show_frame,
    )
    scene = GraphSceneBridge(parent=host)
    scene.bind_graphics_preferences_source(host.shell_workspace_presenter)
    scene.set_workspace(model, registry, model.active_workspace.workspace_id)
    return model, scene, host


class MediaPanelCreationPreferenceTests(unittest.TestCase):
    def test_blank_media_panels_use_current_preference_without_retroactive_changes(
        self,
    ) -> None:
        model, scene, host = _bound_scene(False, show_title=False, show_frame=False)
        first_id = scene.add_node_from_type(MEDIA_PANEL_TYPE_ID, 10.0, 20.0)

        host.shell_workspace_presenter.source_input_exposed = True
        host.shell_workspace_presenter.show_title = True
        host.shell_workspace_presenter.show_frame = True
        host.shell_workspace_presenter.graphics_preferences_changed.emit()
        second_id = scene.add_node_from_type(MEDIA_PANEL_TYPE_ID, 30.0, 40.0)

        workspace = model.active_workspace
        self.assertFalse(workspace.nodes[first_id].exposed_ports["source"])
        self.assertFalse(workspace.nodes[first_id].properties["show_title"])
        self.assertFalse(workspace.nodes[first_id].properties["show_frame"])
        self.assertTrue(workspace.nodes[second_id].exposed_ports["source"])
        self.assertTrue(workspace.nodes[second_id].properties["show_title"])
        self.assertTrue(workspace.nodes[second_id].properties["show_frame"])

    def test_seeded_media_panel_keeps_authored_chrome_under_conflicting_defaults(
        self,
    ) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        node = model.add_node(
            workspace_id,
            MEDIA_PANEL_TYPE_ID,
            "Media Panel",
            10.0,
            20.0,
            properties={"show_title": True, "show_frame": False},
        )
        host = _SceneHost(False, show_title=False, show_frame=True)
        scene = GraphSceneBridge(parent=host)
        scene.bind_graphics_preferences_source(host.shell_workspace_presenter)

        scene.set_workspace(model, registry, workspace_id)

        self.assertTrue(node.properties["show_title"])
        self.assertFalse(node.properties["show_frame"])

    def test_explicit_override_wins_and_does_not_infer_from_authored_source(
        self,
    ) -> None:
        model, scene, _host = _bound_scene(
            False,
            show_title=False,
            show_frame=True,
        )
        authored_id = scene.create_node_from_type(
            type_id=MEDIA_PANEL_TYPE_ID,
            x=10.0,
            y=20.0,
            parent_node_id=None,
            select_node=False,
            property_overrides={
                "source": "example.png",
                "show_title": True,
                "show_frame": False,
            },
        )
        connected_id = scene.create_node_from_type(
            type_id=MEDIA_PANEL_TYPE_ID,
            x=30.0,
            y=40.0,
            parent_node_id=None,
            select_node=False,
            exposed_port_overrides={"source": True},
        )

        workspace = model.active_workspace
        self.assertFalse(workspace.nodes[authored_id].exposed_ports["source"])
        self.assertTrue(workspace.nodes[authored_id].properties["show_title"])
        self.assertFalse(workspace.nodes[authored_id].properties["show_frame"])
        self.assertTrue(workspace.nodes[connected_id].exposed_ports["source"])

    def test_exposure_override_rejects_unknown_port_before_creation(self) -> None:
        model, scene, _host = _bound_scene(True)

        with self.assertRaisesRegex(KeyError, "missing"):
            scene.create_node_from_type(
                type_id=MEDIA_PANEL_TYPE_ID,
                x=10.0,
                y=20.0,
                parent_node_id=None,
                select_node=False,
                exposed_port_overrides={"missing": False},
            )

        self.assertEqual(model.active_workspace.nodes, {})

    def test_project_round_trip_preserves_serialized_source_exposure(self) -> None:
        model, scene, _host = _bound_scene(
            True,
            show_title=False,
            show_frame=True,
        )
        node_id = scene.create_node_from_type(
            type_id=MEDIA_PANEL_TYPE_ID,
            x=10.0,
            y=20.0,
            parent_node_id=None,
            select_node=False,
            property_overrides={"show_title": True, "show_frame": False},
            exposed_port_overrides={"source": False},
        )
        registry = build_default_registry()

        document = JsonProjectSerializer(registry).to_persistent_document(model.project)
        loaded = JsonProjectSerializer(registry).from_document(document)

        loaded_node = loaded.workspaces[model.active_workspace.workspace_id].nodes[
            node_id
        ]
        self.assertFalse(loaded_node.exposed_ports["source"])
        self.assertTrue(loaded_node.properties["show_title"])
        self.assertFalse(loaded_node.properties["show_frame"])

    def test_pasted_media_panel_keeps_authored_chrome_under_conflicting_defaults(
        self,
    ) -> None:
        model, scene, _host = _bound_scene(
            False,
            show_title=False,
            show_frame=True,
        )
        original_id = scene.create_node_from_type(
            type_id=MEDIA_PANEL_TYPE_ID,
            x=10.0,
            y=20.0,
            parent_node_id=None,
            select_node=False,
            property_overrides={"show_title": True, "show_frame": False},
        )
        scene.select_node(original_id, False)
        fragment = scene.serialize_selected_subgraph_fragment()
        self.assertIsNotNone(fragment)
        before_ids = set(model.active_workspace.nodes)

        self.assertTrue(scene.paste_subgraph_fragment(fragment, 300.0, 240.0))

        pasted_ids = set(model.active_workspace.nodes) - before_ids
        self.assertEqual(len(pasted_ids), 1)
        pasted = model.active_workspace.nodes[pasted_ids.pop()]
        self.assertTrue(pasted.properties["show_title"])
        self.assertFalse(pasted.properties["show_frame"])

    def test_explicit_drop_connect_forces_source_exposure(self) -> None:
        workspace = GraphModel().active_workspace
        host = SimpleNamespace(
            runtime_history=SimpleNamespace(
                grouped_action=lambda *args, **kwargs: nullcontext()
            ),
            scene=SimpleNamespace(active_scope_path=()),
        )
        ops = WorkspaceDropConnectController(
            host,  # type: ignore[arg-type]
            active_workspace=lambda: workspace,
            resolve_custom_workflow_definition=lambda _workflow_id: None,
            prompt_connection_candidate=lambda **_kwargs: None,
            effects=SimpleNamespace(),  # type: ignore[arg-type]
        )
        create_calls: list[dict[str, bool] | None] = []
        ops.insert_library_node = (  # type: ignore[method-assign]
            lambda type_id, x, y, *, exposed_port_overrides=None: (
                create_calls.append(exposed_port_overrides) or "created"
            )
        )
        ops.auto_connect_dropped_node_to_port = lambda *args, **kwargs: True  # type: ignore[method-assign]

        result = ops.request_drop_node_from_library(
            MEDIA_PANEL_TYPE_ID,
            10.0,
            20.0,
            "port",
            "target",
            "value",
            "",
        )

        self.assertTrue(result.payload)
        self.assertEqual(create_calls, [{"source": True}])


if __name__ == "__main__":
    unittest.main()
