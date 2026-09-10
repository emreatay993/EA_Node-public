from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from PyQt6.QtCore import QObject, pyqtSignal

from ea_node_editor.ui_qml.viewer_control_bridge import ViewerControlBridge


class _SceneBridgeStub(QObject):
    workspace_changed = pyqtSignal(str)
    nodes_changed = pyqtSignal()

    def __init__(self, node: SimpleNamespace) -> None:
        super().__init__()
        self.workspace_id = "workspace"
        self._node = node

    def set_node_property(self, node_id: str, key: str, value: Any) -> None:
        if node_id != "node":
            raise KeyError(node_id)
        self._node.properties[key] = value
        self.nodes_changed.emit()


class _SessionBridgeStub(QObject):
    viewer_query_completed = pyqtSignal(str, dict)
    sessions_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.sync_calls: list[tuple[str, str, Any, dict[str, Any]]] = []
        self.session_id = "session"

    def sync_node_property_option(
        self,
        node_id: str,
        key: str,
        value: Any,
        context: dict[str, Any],
    ) -> bool:
        self.sync_calls.append((node_id, key, value, dict(context)))
        return True

    def session_state(self, node_id: str) -> dict[str, Any]:
        return {
            "workspace_id": "workspace",
            "node_id": node_id,
            "session_id": self.session_id,
            "summary": {"scene_fingerprint": "a" * 64},
        }

    def query_session(self, **_kwargs: Any) -> dict[str, Any]:
        return {
            "supported": False,
            "value": {},
            "explanation": "The active viewer session is not ready.",
        }


class _ViewerHostStub:
    def __init__(self) -> None:
        self.camera_state: dict[str, Any] = {"zoom": 1.0, "parallel_projection": False}
        self.applied: list[tuple[str, dict[str, Any]]] = []
        self.selection_filters: list[tuple[str, str]] = []
        self.activated: list[tuple[str, list[dict[str, str]]]] = []
        self.selection = {
            "scene_fingerprint": "a" * 64,
            "entities": [
                {
                    "layer_id": "primary",
                    "source_fingerprint": "a" * 64,
                    "entity_kind": "cad_face",
                    "entity_id": f"part:1/face:{value}",
                }
                for value in (8, 2)
            ],
            "isolate_active": False,
            "selection_filter": "cad_face",
        }

    def camera_state_snapshot(self, _node_id: str) -> dict[str, Any]:
        return dict(self.camera_state)

    def apply_overlay_camera_state(self, node_id: str, state: dict[str, Any]) -> bool:
        self.applied.append((node_id, dict(state)))
        return True

    def viewer_selection_snapshot(self, _node_id: str) -> dict[str, Any]:
        return dict(self.selection)

    def activate_viewer_selection(self, _node_id: str, _entities: list[dict[str, str]]) -> bool:
        self.activated.append(
            (_node_id, [dict(entity) for entity in _entities])
        )
        return True

    def set_viewer_selection_filter(self, _node_id: str, _value: str) -> bool:
        self.selection_filters.append((_node_id, _value))
        return True


class _AppPreferencesControllerStub:
    def __init__(self) -> None:
        self.graphics = {"engineering_viewer": {"tangent_selection_angle_degrees": 5.0}}
        self.updates: list[tuple[dict[str, Any], Any]] = []

    def graphics_settings(self) -> dict[str, Any]:
        return self.graphics

    def update_graphics_settings(self, updates: dict[str, Any], *, host=None) -> None:  # noqa: ANN001
        self.updates.append((updates, host))
        self.graphics["engineering_viewer"] = dict(updates["engineering_viewer"])


class ViewerControlBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.node = SimpleNamespace(
            properties={}, title="Viewer", type_id="tests.viewer"
        )
        self.workspace = SimpleNamespace(nodes={"node": self.node})
        self.host = _ViewerHostStub()
        self.preferences = _AppPreferencesControllerStub()
        self.preferences_host = QObject()
        self.current_model = SimpleNamespace(
            project=SimpleNamespace(workspaces={"workspace": self.workspace})
        )
        self.current_registry = SimpleNamespace(
            spec_or_none=lambda _type_id: SimpleNamespace(surface_family="viewer")
        )
        self.provider_calls = {
            "active": 0,
            "workspace": 0,
            "model": 0,
            "registry": 0,
        }

        def active_workspace_id_provider() -> str:
            self.provider_calls["active"] += 1
            return "workspace"

        def workspace_provider(workspace_id: str):  # noqa: ANN202
            self.provider_calls["workspace"] += 1
            return self.current_model.project.workspaces.get(workspace_id)

        def model_provider():  # noqa: ANN202
            self.provider_calls["model"] += 1
            return self.current_model

        def registry_provider():  # noqa: ANN202
            self.provider_calls["registry"] += 1
            return self.current_registry

        self.scene = _SceneBridgeStub(self.node)
        self.session = _SessionBridgeStub()
        self.bridge = ViewerControlBridge(
            self.preferences_host,
            active_workspace_id_provider=active_workspace_id_provider,
            workspace_provider=workspace_provider,
            model_provider=model_provider,
            registry_provider=registry_provider,
            app_preferences_controller=self.preferences,
            save_file_dialog=lambda **_kwargs: "",
            viewer_host_service=self.host,
            scene_bridge=self.scene,
            viewer_session_bridge=self.session,
        )

    def test_node_scoped_options_include_new_render_and_orientation_values(self) -> None:
        changed: list[str] = []
        self.bridge.viewer_control_changed.connect(changed.append)
        self.assertTrue(self.bridge.set_viewer_option("node", "representation", "wireframe_visible_edges"))
        self.assertTrue(self.bridge.set_viewer_option("node", "show_attribute_colors", True))
        self.assertTrue(self.bridge.set_viewer_option("node", "show_orientation_triad", False))
        self.assertTrue(self.bridge.set_viewer_option("node", "show_view_cube", False))
        self.assertTrue(self.bridge.set_viewer_option("node", "show_world_axes", True))
        self.assertTrue(self.bridge.set_viewer_option("node", "colormap", "turbo"))
        self.assertTrue(self.bridge.set_viewer_option("node", "show_scalar_bar", "false"))
        self.assertTrue(self.bridge.set_viewer_option("node", "deform_scale", "-3"))
        self.assertTrue(self.bridge.set_viewer_option("node", "representation", "wireframe"))
        self.assertTrue(self.bridge.set_viewer_option("node", "scene_styles", {"scene_1": {"opacity": 1}}))
        self.assertTrue(self.bridge.set_scene_style("node", "scene_1", "opacity", "0.2"))
        self.assertFalse(self.bridge.set_viewer_option("node", "primary_opacity", "1.5"))
        self.assertFalse(self.bridge.set_viewer_option("node", "overlay_opacity", "0.2"))
        self.assertTrue(self.bridge.set_viewer_option("node", "parallel_projection", True))
        self.assertFalse(self.bridge.set_viewer_option("node", "path", "C:/other.rst"))
        self.assertFalse(self.bridge.set_viewer_option("node", "unknown_key", 1))
        self.assertFalse(self.bridge.set_viewer_option("node", "unsupported", True))
        self.assertEqual(self.node.properties["representation"], "wireframe")
        self.assertEqual(self.node.properties["colormap"], "turbo")
        self.assertIs(self.node.properties["show_scalar_bar"], False)
        self.assertEqual(self.node.properties["deform_scale"], "off")
        self.assertEqual(self.node.properties["scene_styles"], {"scene_1": {"opacity": 0.2, "color": ""}})
        self.assertIs(self.node.properties["parallel_projection"], True)
        self.assertEqual(len(self.session.sync_calls), 12)
        colormap_sync = next(
            call for call in self.session.sync_calls if call[1] == "colormap"
        )
        self.assertEqual(colormap_sync[:3], ("node", "colormap", "turbo"))
        self.assertTrue(changed)
        self.assertEqual(set(changed), {"node"})

    def test_per_scene_styles_validate_and_preserve_other_scenes(self) -> None:
        self.node.properties["scene_input_ids"] = ["scene_1", "scene_2", "scene_3"]
        self.assertTrue(self.bridge.set_scene_style("node", "scene_1", "color", "#123ABC"))
        self.assertTrue(self.bridge.set_scene_style("node", "scene_2", "opacity", "0.3"))
        before = dict(self.node.properties["scene_styles"])
        for scene_id, key, value in [
            ("missing", "color", "#123456"), ("scene_1", "color", "invalid"),
            ("scene_1", "opacity", float("nan")), ("scene_1", "opacity", 1.1),
            ("scene_1", "opacity", -0.1), ("scene_1", "unknown", True),
        ]:
            with self.subTest(scene_id=scene_id, key=key, value=value):
                self.assertFalse(self.bridge.set_scene_style("node", scene_id, key, value))
                self.assertEqual(self.node.properties["scene_styles"], before)
        self.assertTrue(self.bridge.set_scene_style("node", "scene_1", "color", ""))
        self.assertEqual(self.node.properties["scene_styles"]["scene_1"]["color"], "")
        self.assertEqual(self.node.properties["scene_styles"]["scene_2"]["opacity"], 0.3)
        self.assertEqual(self.session.sync_calls[-1][1:3], ("scene_styles", self.node.properties["scene_styles"]))

    def test_export_uses_live_scene_visibility_and_styles(self) -> None:
        self.bridge._save_file_dialog = lambda **_kwargs: "C:/tmp/scenes.vtm"
        display_state = {"layer_visibility": {"scene_1": False, "scene_2": True},
                         "scene_styles": {"scene_2": {"opacity": 0.4, "color": "#123456"}}}
        self.host.viewer_render_stats = lambda _node_id: {"display_state": display_state}
        with patch.object(self.session, "query_session", return_value={"supported": True}) as query:
            self.assertTrue(self.bridge.export_engineering_viewer("node", "vtm")["supported"])
        self.assertEqual(query.call_args.kwargs["payload"]["display_state"], display_state)
        self.assertEqual(query.call_args.kwargs["payload"]["path"], "C:/tmp/scenes.vtm")
        self.assertNotIn("output_path", query.call_args.kwargs["payload"])

    def test_direct_providers_follow_model_and_registry_replacement_and_fail_closed(
        self,
    ) -> None:
        resolved = self.bridge._node_properties("node")  # noqa: SLF001
        self.assertIsNotNone(resolved)
        self.assertIs(resolved[1], self.node)
        self.assertEqual(
            self.provider_calls,
            {"active": 1, "workspace": 1, "model": 1, "registry": 1},
        )

        replacement_node = SimpleNamespace(
            properties={"representation": "surface"},
            title="Replacement",
            type_id="tests.viewer.replacement",
        )
        replacement_workspace = SimpleNamespace(nodes={"node": replacement_node})
        self.current_model = SimpleNamespace(
            project=SimpleNamespace(workspaces={"workspace": replacement_workspace})
        )
        self.current_registry = SimpleNamespace(
            spec_or_none=lambda _type_id: SimpleNamespace(surface_family="viewer")
        )
        replaced = self.bridge._node_properties("node")  # noqa: SLF001
        self.assertIsNotNone(replaced)
        self.assertIs(replaced[1], replacement_node)
        self.assertEqual(
            self.provider_calls,
            {"active": 2, "workspace": 2, "model": 2, "registry": 2},
        )

        self.current_registry = SimpleNamespace(
            spec_or_none=lambda _type_id: SimpleNamespace(surface_family="table")
        )
        self.assertIsNone(self.bridge._node_properties("node"))  # noqa: SLF001
        self.assertEqual(
            self.provider_calls,
            {"active": 3, "workspace": 3, "model": 3, "registry": 3},
        )

        self.scene.workspace_id = "different-workspace"
        self.assertIsNone(self.bridge._active_workspace())  # noqa: SLF001
        self.assertEqual(
            self.provider_calls,
            {"active": 4, "workspace": 3, "model": 3, "registry": 3},
        )

    def test_selection_filter_is_runtime_only_and_tangent_angle_is_app_wide(self) -> None:
        self.assertTrue(self.bridge.set_viewer_option("node", "selection_filter", "CAD_FACE"))
        self.assertEqual(self.host.selection_filters, [("node", "cad_face")])
        self.assertNotIn("selection_filter", self.node.properties)
        self.assertEqual(self.session.sync_calls, [])

        changed: list[float] = []
        self.bridge.viewer_tangent_selection_angle_changed.connect(changed.append)
        self.assertEqual(self.bridge.viewer_tangent_selection_angle_degrees(), 5.0)
        self.assertTrue(self.bridge.set_viewer_tangent_selection_angle_degrees(120.0))
        self.assertEqual(changed, [90.0])
        self.assertEqual(
            self.preferences.updates,
            [
                (
                    {"engineering_viewer": {"tangent_selection_angle_degrees": 90.0}},
                    self.preferences_host,
                )
            ],
        )

    def test_saved_views_persist_order_cycle_with_wrap_and_sync_projection(self) -> None:
        front = {
            "position": [1.0, 2.0, 3.0],
            "focal_point": [0.0, 0.0, 0.0],
            "viewup": [0.0, 1.0, 0.0],
            "zoom": 1.25,
            "parallel_scale": 4.5,
            "view_angle": 30.0,
            "parallel_projection": False,
        }
        rear = {
            "position": [-3.0, 2.0, 1.0],
            "focal_point": [1.0, 0.0, 0.0],
            "viewup": [0.0, 0.0, 1.0],
            "zoom": 2.0,
            "parallel_scale": 7.5,
            "view_angle": 24.0,
            "parallel_projection": True,
        }
        self.assertEqual(self.bridge.viewer_camera_bookmark_current_index("node"), -1)
        self.host.camera_state = front
        self.assertTrue(self.bridge.save_viewer_camera_bookmark("node", "Front"))
        self.assertEqual(self.bridge.viewer_camera_bookmark_current_index("node"), 0)
        self.host.camera_state = rear
        self.assertTrue(self.bridge.save_viewer_camera_bookmark("node", "Back"))
        self.assertEqual(self.bridge.viewer_camera_bookmark_current_index("node"), 1)
        self.assertTrue(self.bridge.rename_viewer_camera_bookmark("node", 1, "Rear"))
        self.assertEqual(self.bridge.viewer_camera_bookmark_current_index("node"), 1)
        self.assertTrue(self.bridge.move_viewer_camera_bookmark("node", 1, -1))
        self.assertEqual(self.bridge.viewer_camera_bookmark_current_index("node"), 0)
        self.assertEqual(
            [entry["name"] for entry in self.bridge.viewer_camera_bookmarks("node")],
            ["Rear", "Front"],
        )

        self.assertTrue(self.bridge.cycle_viewer_camera_bookmark("node", -1))
        self.assertEqual(self.bridge.viewer_camera_bookmark_current_index("node"), 1)
        expected_front = {
            **front,
            "clip_enabled": False,
            "clip_axis": "x",
            "clip_offset": 0.0,
        }
        expected_rear = {
            **rear,
            "clip_enabled": False,
            "clip_axis": "x",
            "clip_offset": 0.0,
        }
        self.assertEqual(self.host.applied[-1], ("node", expected_front))
        self.assertTrue(self.bridge.apply_viewer_camera_bookmark("node", 0))
        self.assertEqual(self.bridge.viewer_camera_bookmark_current_index("node"), 0)
        self.assertEqual(self.host.applied[-1], ("node", expected_rear))
        self.assertIs(self.node.properties["parallel_projection"], True)
        self.assertFalse(self.bridge.apply_viewer_camera_bookmark("node", 99))
        self.assertFalse(self.bridge.remove_viewer_camera_bookmark("node", 99))

        self.session.session_id = "replacement-session"
        self.session.sessions_changed.emit()
        self.assertNotIn(("workspace", "node"), self.bridge._bookmark_indices)
        self.assertEqual(self.bridge.viewer_camera_bookmark_current_index("node"), -1)
        self.assertTrue(self.bridge.cycle_viewer_camera_bookmark("node", -1))
        self.assertEqual(self.bridge.viewer_camera_bookmark_current_index("node"), 1)
        self.assertEqual(self.host.applied[-1], ("node", expected_front))

        self.workspace.nodes.clear()
        self.scene.nodes_changed.emit()
        self.assertEqual(self.bridge.viewer_camera_bookmark_current_index("node"), -1)
        self.assertEqual(self.bridge._bookmark_indices, {})
        self.assertEqual(self.bridge._bookmark_session_ids, {})

    def test_saved_view_current_index_tracks_removal_without_selecting_an_unapplied_view(self) -> None:
        for name, zoom in (("A", 1.0), ("B", 2.0), ("C", 3.0)):
            self.host.camera_state = {"zoom": zoom}
            self.assertTrue(self.bridge.save_viewer_camera_bookmark("node", name))

        self.assertTrue(self.bridge.apply_viewer_camera_bookmark("node", 1))
        self.assertEqual(self.bridge.viewer_camera_bookmark_current_index("node"), 1)
        self.assertTrue(self.bridge.remove_viewer_camera_bookmark("node", 0))
        self.assertEqual(self.bridge.viewer_camera_bookmark_current_index("node"), 0)
        self.assertTrue(self.bridge.remove_viewer_camera_bookmark("node", 0))
        self.assertEqual(self.bridge.viewer_camera_bookmark_current_index("node"), -1)
        self.assertTrue(self.bridge.cycle_viewer_camera_bookmark("node", 1))
        self.assertEqual(self.bridge.viewer_camera_bookmark_current_index("node"), 0)

    def test_saved_selections_remain_node_scoped(self) -> None:
        self.assertTrue(self.bridge.save_current_viewer_selection("node", "Faces"))
        saved = self.bridge.viewer_saved_selections("node")
        self.assertEqual(
            [entity["entity_id"] for entity in saved["selections"][0]["entities"]],
            ["part:1/face:2", "part:1/face:8"],
        )
        self.assertTrue(self.bridge.rename_viewer_selection("node", 0, "Critical faces"))
        self.assertTrue(self.bridge.activate_viewer_selection("node", 0))
        self.assertEqual(
            self.host.activated,
            [("node", saved["selections"][0]["entities"])],
        )
        self.assertTrue(self.bridge.publish_viewer_selection("node", 0))
        self.assertEqual(
            self.bridge.viewer_saved_selections("node")["published_name"],
            "Critical faces",
        )
        self.assertTrue(self.bridge.remove_viewer_selection("node", 0))
        self.assertEqual(self.bridge.viewer_saved_selections("node")["selections"], [])
        self.assertTrue(self.bridge.viewer_query_available())
        unavailable = self.bridge.query_viewer("node", "bounds", {})
        self.assertFalse(unavailable["supported"])
        self.assertIn("not ready", unavailable["explanation"])

    def test_stale_saved_selection_schema_cannot_break_viewer_controls(self) -> None:
        self.node.properties["saved_selections"] = {
            "schema": "engineering_selection_set.v1",
            "scene_fingerprint": "",
            "published_name": "",
            "selections": [],
        }

        with patch(
            "ea_node_editor.ui_qml.viewer_control_bridge.normalize_engineering_selection_set",
            side_effect=AssertionError("stale schema must be rejected before normalization"),
        ):
            saved = self.bridge.viewer_saved_selections("node")

        self.assertEqual(saved["schema"], "engineering_selection_set.v2")
        self.assertEqual(saved["scene_fingerprint"], "a" * 64)
        self.assertEqual(saved["published_name"], "")
        self.assertEqual(saved["selections"], [])


if __name__ == "__main__":
    unittest.main()
