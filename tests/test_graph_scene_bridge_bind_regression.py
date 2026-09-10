from __future__ import annotations

import copy
import importlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from PyQt6.QtCore import QObject, QPointF, pyqtSignal

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.records import NodeLinkRecord
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.builtins.media_panel import MEDIA_PANEL_TYPE_ID
from ea_node_editor.nodes.builtins.passive_annotation import PASSIVE_ANNOTATION_TEXT_TYPE_ID
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.ui.shell.runtime_history import (
    ACTION_ADD_EDGE,
    ACTION_MOVE_NODE,
    ACTION_RENAME_NODE,
    RuntimeGraphHistory,
)
from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge
from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
from ea_node_editor.ui_qml.graph_scene.command_bridge import GraphSceneCommandBridge
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge

_REPO_ROOT = Path(__file__).resolve().parents[1]
GROUP_BACKDROP_TYPE_ID = "passive.annotation.group_backdrop"
LOGGER_TYPE_ID = "core.logger"


class _ExpandCollisionPreferenceSource(QObject):
    graphics_preferences_changed = pyqtSignal()

    def __init__(self, settings: dict[str, object]) -> None:
        super().__init__()
        self.graphics_expand_collision_avoidance = dict(settings)


class _SceneGraphicsPreferenceSource(QObject):
    graphics_preferences_changed = pyqtSignal()

    def __init__(
        self,
        *,
        show_port_labels: bool = True,
        graph_label_pixel_size: int = 10,
        node_title_icon_pixel_size: int = 10,
        lightweight_canvas: bool = False,
    ) -> None:
        super().__init__()
        self.graphics_show_port_labels = bool(show_port_labels)
        self.graphics_graph_label_pixel_size = int(graph_label_pixel_size)
        self.graphics_node_title_icon_pixel_size = int(node_title_icon_pixel_size)
        self.graphics_lightweight_canvas = bool(lightweight_canvas)


class _CountingRuntimeGraphHistory(RuntimeGraphHistory):
    def __init__(self) -> None:
        super().__init__()
        self.capture_count = 0

    def capture_workspace(self, workspace):  # noqa: ANN001
        self.capture_count += 1
        return super().capture_workspace(workspace)


class _EdgeRewireCanvasSource:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str, str, str, bool, bool]] = []

    def request_rewire_edges(
        self,
        edge_ids: list[str],
        endpoint: str,
        node_id: str,
        port_key: str,
        copy_requested: bool = False,
        append_requested: bool = False,
    ) -> bool:
        self.calls.append(
            (
                list(edge_ids),
                endpoint,
                node_id,
                port_key,
                copy_requested,
                append_requested,
            )
        )
        return True


class _SceneBridgeForNodeLinkTests(QObject):
    pending_surface_action_changed = pyqtSignal()

    def __init__(self, model: GraphModel, workspace_id: str) -> None:
        super().__init__()
        self._model = model
        self._workspace_id = workspace_id


class _AuthoringBoundaryForNodeLinkTests:
    def __init__(self, model: GraphModel, workspace_id: str) -> None:
        self.model = model
        self.workspace_id = workspace_id
        self.focus_calls: list[str] = []
        self.property_calls: list[tuple[str, str, object]] = []

    def focus_node(self, node_id: str) -> QPointF:
        self.focus_calls.append(str(node_id))
        return QPointF(10.0, 20.0)

    def set_node_property(self, node_id: str, key: str, value: object) -> None:
        self.property_calls.append((str(node_id), str(key), value))
        self.model.set_node_property(self.workspace_id, str(node_id), str(key), value)


class _BatchEdgeAuthoringBoundary:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.rewire_result = True
        self.display_mode_result = True

    def request_rewire_edges(
        self,
        edge_ids: list[object],
        endpoint: str,
        node_id: str,
        port_key: str,
        copy_requested: bool,
        append_requested: bool,
    ) -> bool:
        self.calls.append(
            (
                "request_rewire_edges",
                (
                    list(edge_ids),
                    endpoint,
                    node_id,
                    port_key,
                    copy_requested,
                    append_requested,
                ),
            )
        )
        return self.rewire_result

    def set_edges_display_mode(self, edge_ids: list[object], mode: str) -> bool:
        self.calls.append(("set_edges_display_mode", (list(edge_ids), mode)))
        return self.display_mode_result


class GraphSceneCommandBridgeContractTests(unittest.TestCase):
    def test_scene_command_bridge_rejects_cross_workspace_node_link(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        source = model.add_node(
            workspace.workspace_id,
            "core.logger",
            "Source",
            40.0,
            60.0,
        )
        workspace.nodes[source.node_id].links.append(
            NodeLinkRecord(
                link_id="link-cross-node",
                kind="node",
                title="Target",
                target="node-target",
                target_workspace_id="workspace-target",
                target_node_id="node-target",
            )
        )
        authoring = _AuthoringBoundaryForNodeLinkTests(model, workspace.workspace_id)
        bridge = GraphSceneCommandBridge(
            _SceneBridgeForNodeLinkTests(model, workspace.workspace_id),
            scope_selection=SimpleNamespace(),
            authoring_boundary=authoring,
            pending_surface_action=SimpleNamespace(node_id=""),
        )

        self.assertFalse(bridge.open_node_link(source.node_id, "link-cross-node"))
        self.assertEqual(authoring.focus_calls, [])

    def test_scene_command_bridge_opens_video_timestamp_node_link_and_updates_position(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            video_path = Path(temporary_directory) / "clip.mp4"
            video_path.write_bytes(b"video")
            model = GraphModel()
            workspace = model.active_workspace
            video = model.add_node(
                workspace.workspace_id,
                MEDIA_PANEL_TYPE_ID,
                "Media Panel",
                40.0,
                60.0,
                properties={"source": str(video_path), "position_ms": 0},
                exposed_ports={"source": False},
            )
            note = model.add_node(
                workspace.workspace_id,
                PASSIVE_ANNOTATION_TEXT_TYPE_ID,
                "Video note",
                240.0,
                60.0,
            )
            workspace.nodes[note.node_id].links.append(
                NodeLinkRecord(
                    link_id="link-video-time",
                    kind="node",
                    title="Video 0:07",
                    target=video.node_id,
                    subtitle="video_position_ms=7777",
                )
            )
            authoring = _AuthoringBoundaryForNodeLinkTests(model, workspace.workspace_id)
            bridge = GraphSceneCommandBridge(
                _SceneBridgeForNodeLinkTests(model, workspace.workspace_id),
                scope_selection=SimpleNamespace(),
                authoring_boundary=authoring,
                pending_surface_action=SimpleNamespace(node_id=""),
            )

            self.assertTrue(bridge.open_node_link(note.node_id, "link-video-time"))
            self.assertEqual(authoring.property_calls, [(video.node_id, "position_ms", 7777)])
            self.assertEqual(authoring.focus_calls, [video.node_id])
            self.assertEqual(workspace.nodes[video.node_id].properties["position_ms"], 7777)

    def test_scene_command_bridge_focuses_nonready_media_timestamp_target_without_seeking(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        media = model.add_node(
            workspace.workspace_id,
            MEDIA_PANEL_TYPE_ID,
            "Media Panel",
            40.0,
            60.0,
            properties={"source": "C:/dormant/clip.mp4", "position_ms": 0},
            exposed_ports={"source": True},
        )
        note = model.add_node(
            workspace.workspace_id,
            PASSIVE_ANNOTATION_TEXT_TYPE_ID,
            "Video note",
            240.0,
            60.0,
        )
        workspace.nodes[note.node_id].links.append(
            NodeLinkRecord(
                link_id="link-video-time",
                kind="node",
                title="Video 0:07",
                target=media.node_id,
                subtitle="video_position_ms=7777",
            )
        )
        authoring = _AuthoringBoundaryForNodeLinkTests(model, workspace.workspace_id)
        bridge = GraphSceneCommandBridge(
            _SceneBridgeForNodeLinkTests(model, workspace.workspace_id),
            scope_selection=SimpleNamespace(),
            authoring_boundary=authoring,
            pending_surface_action=SimpleNamespace(node_id=""),
        )

        self.assertTrue(bridge.open_node_link(note.node_id, "link-video-time"))
        self.assertEqual(authoring.property_calls, [])
        self.assertEqual(authoring.focus_calls, [media.node_id])
        self.assertEqual(workspace.nodes[media.node_id].properties["position_ms"], 0)

    def test_scene_command_bridge_forwards_batch_rewire_and_display_mode_results(self) -> None:
        scene = _SceneBridgeForNodeLinkTests(GraphModel(), "workspace-1")
        authoring = _BatchEdgeAuthoringBoundary()
        bridge = GraphSceneCommandBridge(
            scene,
            scope_selection=SimpleNamespace(),
            authoring_boundary=authoring,
            pending_surface_action=SimpleNamespace(node_id=""),
        )

        self.assertTrue(
            bridge.request_rewire_edges(
                ["edge-2", "edge-1"],
                "target",
                "sink-node",
                "payload",
                True,
                True,
            )
        )
        self.assertTrue(bridge.set_edges_display_mode(["edge-1", "edge-2"], "faint"))
        authoring.rewire_result = False
        authoring.display_mode_result = False
        self.assertFalse(
            bridge.request_rewire_edges(
                ["edge-1"], "source", "", "", False, False
            )
        )
        self.assertFalse(bridge.set_edges_display_mode(["edge-1"], "hidden"))
        self.assertEqual(
            authoring.calls,
            [
                (
                    "request_rewire_edges",
                    (
                        ["edge-2", "edge-1"],
                        "target",
                        "sink-node",
                        "payload",
                        True,
                        True,
                    ),
                ),
                ("set_edges_display_mode", (["edge-1", "edge-2"], "faint")),
                (
                    "request_rewire_edges",
                    (["edge-1"], "source", "", "", False, False),
                ),
                ("set_edges_display_mode", (["edge-1"], "hidden")),
            ],
        )


class GraphSceneBridgeBindRegressionTests(unittest.TestCase):
    def test_graphics_preferences_source_binding_lifecycle_and_fingerprint(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)
        source = _SceneGraphicsPreferenceSource()
        replacement = _SceneGraphicsPreferenceSource(
            show_port_labels=False,
            graph_label_pixel_size=14,
            node_title_icon_pixel_size=12,
            lightweight_canvas=True,
        )
        rebuilds: list[str] = []
        original_rebuild = scene._scene_context.rebuild_models

        def _record_rebuild() -> None:
            rebuilds.append("rebuild")
            original_rebuild()

        scene._scene_context.rebuild_models = _record_rebuild
        try:
            self.assertTrue(scene.bind_graphics_preferences_source(source))
            self.assertEqual(rebuilds, [])
            self.assertFalse(scene.bind_graphics_preferences_source(source))
            with self.assertRaises(TypeError):
                scene.bind_graphics_preferences_source(object())

            source.graphics_show_port_labels = False
            source.graphics_preferences_changed.emit()
            self.assertEqual(rebuilds, ["rebuild"])

            self.assertTrue(scene.bind_graphics_preferences_source(replacement))
            self.assertEqual(rebuilds, ["rebuild", "rebuild"])
            self.assertEqual(
                scene._scene_payload_graphics_preferences,
                (False, 14, 12, True, False),
            )

            source.graphics_show_port_labels = True
            source.graphics_preferences_changed.emit()
            self.assertEqual(rebuilds, ["rebuild", "rebuild"])

            self.assertTrue(scene.bind_graphics_preferences_source(None))
            self.assertEqual(rebuilds, ["rebuild", "rebuild", "rebuild"])
            replacement.graphics_show_port_labels = True
            replacement.graphics_preferences_changed.emit()
            self.assertEqual(rebuilds, ["rebuild", "rebuild", "rebuild"])
        finally:
            scene._scene_context.rebuild_models = original_rebuild

    def test_library_drop_preview_forwards_all_graphics_payload_facts(self) -> None:
        source = _SceneGraphicsPreferenceSource(
            show_port_labels=False,
            graph_label_pixel_size=16,
            node_title_icon_pixel_size=12,
            lightweight_canvas=True,
        )
        model = GraphModel()
        registry = build_default_registry()
        scene = GraphSceneBridge()
        scene.bind_graphics_preferences_source(source)
        scene.set_workspace(model, registry, model.active_workspace.workspace_id)
        original_build = scene._payload_builder.build_library_preview_node_payload

        with patch.object(
            scene._payload_builder,
            "build_library_preview_node_payload",
            wraps=original_build,
        ) as build_preview:
            payload = scene.library_drop_preview_payload(
                {"type_id": "core.logger", "display_name": "Logger"}
            )

        self.assertEqual(payload["type_id"], "core.logger")
        self.assertEqual(
            {
                name: build_preview.call_args.kwargs[name]
                for name in (
                    "show_port_labels",
                    "graph_label_pixel_size",
                    "graph_node_icon_pixel_size",
                    "lightweight_canvas",
                )
            },
            {
                "show_port_labels": False,
                "graph_label_pixel_size": 16,
                "graph_node_icon_pixel_size": 12,
                "lightweight_canvas": True,
            },
        )

    def test_scene_registry_replace_never_normalizes_open_graph_data(self) -> None:
        active_registry = build_default_registry()
        replacement_registry = NodeRegistry()
        replacement_registry.freeze()
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(
            workspace.workspace_id,
            "core.constant",
            "Preserved",
            0.0,
            0.0,
            properties={"value": "authored"},
        )
        workspace.dirty = False
        workspace.mutation_revision = 11
        snapshot = workspace.capture_snapshot()
        project_revision = model.project.project_document_revision
        scene = GraphSceneBridge()
        scene.set_workspace(model, active_registry, workspace.workspace_id)

        scene.replace_registry(replacement_registry)

        self.assertIs(scene._registry, replacement_registry)
        self.assertEqual(workspace.capture_snapshot(), snapshot)
        self.assertEqual(workspace.mutation_revision, 11)
        self.assertEqual(model.project.project_document_revision, project_revision)
        self.assertIn(node.node_id, workspace.nodes)

    def test_scene_registry_replace_restores_payloads_on_publication_failure(
        self,
    ) -> None:
        active_registry = build_default_registry()
        replacement_registry = NodeRegistry()
        replacement_registry.freeze()
        model = GraphModel()
        workspace = model.active_workspace
        model.add_node(
            workspace.workspace_id,
            "core.constant",
            "Preserved",
            0.0,
            0.0,
        )
        scene = GraphSceneBridge()
        scene.set_workspace(model, active_registry, workspace.workspace_id)
        cache_before = copy.deepcopy(scene._payload_cache)
        nodes_before = copy.deepcopy(scene.nodes_model)
        edges_before = copy.deepcopy(scene.edges_model)
        real_rebuild_models = scene._scene_context.rebuild_models

        def rebuild_then_fail() -> None:
            real_rebuild_models()
            raise RuntimeError("payload publication failed")

        with (
            patch.object(
                scene._scene_context,
                "rebuild_models",
                side_effect=rebuild_then_fail,
            ),
            self.assertRaisesRegex(RuntimeError, "payload publication failed"),
        ):
            scene.replace_registry(replacement_registry)

        self.assertIs(scene._registry, active_registry)
        self.assertEqual(scene._payload_cache, cache_before)
        self.assertEqual(scene.nodes_model, nodes_before)
        self.assertEqual(scene.edges_model, edges_before)

    def test_scene_registry_rebuild_restores_project_and_scene_on_publication_failure(
        self,
    ) -> None:
        active_registry = build_default_registry()
        replacement_registry = NodeRegistry()
        model = GraphModel()
        primary_workspace = model.active_workspace
        source = model.add_node(
            primary_workspace.workspace_id,
            "core.constant",
            "Preserved Source",
            0.0,
            0.0,
            properties={"value": "preserved"},
            exposed_ports={"value": True},
        )
        target = model.add_node(
            primary_workspace.workspace_id,
            "core.python_script",
            "Preserved Target",
            280.0,
            0.0,
            properties={"code": "return inputs"},
        )
        source.port_labels = {"value": "Preserved Value"}
        source.port_modifiers = {"value": ("graft",)}
        target.principal_input_port_id = "payload"
        edge = model.add_edge(
            primary_workspace.workspace_id,
            source.node_id,
            "value",
            target.node_id,
            "payload",
            label="Preserved Edge",
            visual_style={"stroke": "#123456"},
        )
        edge.enabled = False
        edge.input_order = 7
        primary_workspace.dirty = False

        secondary_workspace = model.create_workspace("Secondary")
        parent = model.add_node(
            secondary_workspace.workspace_id,
            "core.constant",
            "Preserved Parent",
            0.0,
            0.0,
        )
        child = model.add_node(
            secondary_workspace.workspace_id,
            "core.logger",
            "Preserved Child",
            240.0,
            0.0,
            properties={"message": "secondary"},
        )
        child.parent_node_id = parent.node_id
        secondary_workspace.dirty = True
        model.set_active_workspace(primary_workspace.workspace_id)

        scene = GraphSceneBridge()
        canvas_state = GraphCanvasStateBridge(scene_bridge=scene)
        scene.set_workspace(
            model,
            active_registry,
            primary_workspace.workspace_id,
        )
        scene._state_bridge.node_delta_payload = {
            "kind": "node_delta",
            "reason": "preserved",
        }
        primary_workspace.mutation_revision = 2
        secondary_workspace.mutation_revision = 5

        project = model.project
        workspace_order_before = tuple(project.workspaces)
        project_state_before = (
            project.active_workspace_id,
            project.project_document_revision,
            copy.deepcopy(project.metadata),
        )
        snapshots_before = {
            workspace_id: workspace.capture_snapshot()
            for workspace_id, workspace in project.workspaces.items()
        }
        cache_before = copy.deepcopy(scene._payload_cache)
        node_delta_before = copy.deepcopy(scene._state_bridge.node_delta_payload)
        scene_nodes_before = copy.deepcopy(scene.nodes_model)
        scene_edges_before = copy.deepcopy(scene.edges_model)
        canvas_nodes_before = copy.deepcopy(canvas_state.nodes_model)
        canvas_edges_before = copy.deepcopy(canvas_state.edges_model)
        node_notifications: list[str] = []
        edge_notifications: list[str] = []
        scene.nodes_changed.connect(lambda: node_notifications.append("nodes"))
        scene.edges_changed.connect(lambda: edge_notifications.append("edges"))

        real_rebuild_models = scene._scene_context.rebuild_models

        def publish_replacement_then_fail() -> None:
            real_rebuild_models()
            if scene._registry is replacement_registry:
                self.assertNotIn(source.node_id, primary_workspace.nodes)
                self.assertNotIn(edge.edge_id, primary_workspace.edges)
                self.assertEqual(scene.nodes_model, [])
                self.assertEqual(scene.edges_model, [])
                raise RuntimeError("scene publication failed")

        with (
            patch.object(
                scene._scene_context,
                "rebuild_models",
                side_effect=publish_replacement_then_fail,
            ),
            self.assertRaisesRegex(RuntimeError, "scene publication failed"),
        ):
            scene.rebuild_registry(replacement_registry)

        self.assertIs(scene._registry, active_registry)
        self.assertEqual(tuple(project.workspaces), workspace_order_before)
        self.assertEqual(
            (
                project.active_workspace_id,
                project.project_document_revision,
                project.metadata,
            ),
            project_state_before,
        )
        self.assertEqual(
            {
                workspace_id: workspace.capture_snapshot()
                for workspace_id, workspace in project.workspaces.items()
            },
            snapshots_before,
        )
        self.assertFalse(primary_workspace.dirty)
        self.assertTrue(secondary_workspace.dirty)
        self.assertEqual(primary_workspace.mutation_revision, 2)
        self.assertEqual(secondary_workspace.mutation_revision, 5)
        self.assertEqual(
            primary_workspace.nodes[source.node_id].properties,
            {"value": "preserved"},
        )
        self.assertEqual(
            primary_workspace.nodes[source.node_id].port_labels,
            {"value": "Preserved Value"},
        )
        self.assertEqual(
            primary_workspace.nodes[source.node_id].port_modifiers,
            {"value": ("graft",)},
        )
        self.assertEqual(
            primary_workspace.nodes[target.node_id].principal_input_port_id,
            "payload",
        )
        self.assertEqual(
            primary_workspace.edges[edge.edge_id].input_order,
            7,
        )
        self.assertEqual(
            secondary_workspace.nodes[child.node_id].parent_node_id,
            parent.node_id,
        )
        self.assertEqual(scene._payload_cache, cache_before)
        self.assertEqual(scene._state_bridge.node_delta_payload, node_delta_before)
        self.assertEqual(scene.nodes_model, scene_nodes_before)
        self.assertEqual(scene.edges_model, scene_edges_before)
        self.assertEqual(canvas_state.nodes_model, canvas_nodes_before)
        self.assertEqual(canvas_state.edges_model, canvas_edges_before)
        self.assertEqual(node_notifications, ["nodes", "nodes"])
        self.assertEqual(edge_notifications, ["edges", "edges"])

    def test_scene_bridge_routes_fragment_and_delete_flows_through_authoring_boundary(self) -> None:
        support_text = (
            _REPO_ROOT / "ea_node_editor" / "ui_qml" / "graph_scene" / "state_support.py"
        ).read_text(encoding="utf-8")
        helper_text = (
            _REPO_ROOT / "ea_node_editor" / "ui_qml" / "graph_scene_mutation_history.py"
        ).read_text(encoding="utf-8")

        self.assertIn("return self._command_bridge.duplicate_selected_subgraph()", support_text)
        self.assertIn("return self._command_bridge.serialize_selected_subgraph_fragment()", support_text)
        self.assertIn("return self._command_bridge.paste_subgraph_fragment(", support_text)
        self.assertIn("return self._command_bridge.delete_selected_graph_items(edge_ids)", support_text)
        self.assertIn("def delete_selected_graph_items(self, edge_ids: list[Any]) -> bool:", helper_text)
        self.assertIn("mutations = self._record_mutations()", helper_text)
        self.assertIn("def _expanded_selected_node_ids_for_fragment(", helper_text)

    def test_scene_bridge_keeps_payload_cache_and_pending_surface_action_state_in_focused_helpers(self) -> None:
        bridge_text = (_REPO_ROOT / "ea_node_editor" / "ui_qml" / "graph_scene_bridge.py").read_text(encoding="utf-8")
        package_root = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "graph_scene"
        state_support_text = (package_root / "state_support.py").read_text(encoding="utf-8")
        read_text = (package_root / "read_bridge.py").read_text(encoding="utf-8")
        command_text = (package_root / "command_bridge.py").read_text(encoding="utf-8")
        policy_text = (package_root / "policy_bridge.py").read_text(encoding="utf-8")
        context_text = (package_root / "context.py").read_text(encoding="utf-8")
        package_text = (package_root / "__init__.py").read_text(encoding="utf-8")

        self.assertTrue(package_root.is_dir())
        self.assertIn("from ea_node_editor.ui_qml.graph_scene import (", bridge_text)
        self.assertIn("self._payload_cache = _GraphScenePayloadCache()", bridge_text)
        self.assertIn("self._pending_surface_action = _GraphScenePendingSurfaceAction()", bridge_text)
        self.assertIn("self._state_bridge = GraphSceneReadBridge(self)", bridge_text)
        self.assertIn("self._command_bridge = GraphSceneCommandBridge(", bridge_text)
        self.assertIn("self._policy_bridge = GraphScenePolicyBridge(self, self._policy_boundary)", bridge_text)
        self.assertIn("class _GraphScenePayloadCache:", state_support_text)
        self.assertIn("class _GraphScenePendingSurfaceAction:", state_support_text)
        self.assertIn("class GraphSceneBridgeBase(QObject):", state_support_text)
        self.assertIn("class GraphSceneReadBridge(QObject):", read_text)
        self.assertIn("class GraphSceneCommandBridge(QObject):", command_text)
        self.assertIn("class GraphScenePolicyBridge(QObject):", policy_text)
        self.assertIn("class _GraphSceneContext:", context_text)
        self.assertIn("self._bridge._payload_cache.update(", context_text)
        self.assertIn("GraphSceneBridgeBase", package_text)
        self.assertIn("GraphSceneCommandBridge", package_text)
        self.assertIn("GraphScenePolicyBridge", package_text)
        self.assertIn("GraphSceneReadBridge", package_text)

    def test_scene_bridge_exposes_batch_rewire_and_optional_filter_slots_through_split_command_surface(self) -> None:
        package_root = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "graph_scene"
        command_text = (package_root / "command_bridge.py").read_text(encoding="utf-8")
        state_support_text = (package_root / "state_support.py").read_text(encoding="utf-8")
        helper_text = (
            _REPO_ROOT / "ea_node_editor" / "ui_qml" / "graph_scene_mutation_history.py"
        ).read_text(encoding="utf-8")
        selection_text = (
            _REPO_ROOT / "ea_node_editor" / "ui_qml" / "graph_scene_mutation" / "selection_and_scope_ops.py"
        ).read_text(encoding="utf-8")
        delegate_text = (
            _REPO_ROOT
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph_canvas"
            / "GraphCanvasNodeDelegate.qml"
        ).read_text(encoding="utf-8")

        for snippet, text in (
            ("def request_rewire_edges(", command_text),
            ("def set_hide_optional_ports(self, hide_optional_ports: bool) -> bool:", command_text),
            ("def request_rewire_edges(", state_support_text),
            ("def set_hide_optional_ports(self, hide_optional_ports: bool) -> bool:", state_support_text),
            ("def set_node_settings_group_expanded(", command_text),
            ("def set_node_settings_group_expanded(", state_support_text),
            ("GraphSceneMutationHistory.move_edge_endpoint = _selection_ops.move_edge_endpoint", helper_text),
            ("GraphSceneMutationHistory.set_hide_optional_ports = (", helper_text),
            ("def move_edge_endpoint(", selection_text),
            ("def set_hide_optional_ports(self, hide_optional_ports: bool) -> bool:", selection_text),
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, text)

        self.assertIn("onSettingsGroupExpansionRequested", delegate_text)
        self.assertIn("bridge.set_node_settings_group_expanded", delegate_text)

        scene = GraphSceneBridge()
        scene_meta = scene.metaObject()
        command_meta = scene.command_bridge.metaObject()
        for signature in (
            b"request_rewire_edges(QVariantList,QString,QString,QString,bool,bool)",
            b"set_hide_optional_ports(bool)",
            b"set_node_collapsed(QString,bool)",
            b"set_node_settings_group_expanded(QString,QString,bool)",
        ):
            with self.subTest(signature=signature):
                self.assertGreaterEqual(scene_meta.indexOfMethod(signature), 0)
                self.assertGreaterEqual(command_meta.indexOfMethod(signature), 0)
        for meta in (scene_meta, command_meta):
            self.assertLess(
                meta.indexOfMethod(b"move_edge_endpoint(QString,QString,QString,QString,bool)"),
                0,
            )

    def test_split_command_surface_toggles_only_collapsible_nodes(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)

        collapsible_id = scene.add_node_from_type("core.logger", 0.0, 0.0)
        fixed_id = scene.add_node_from_type("core.trigger", 280.0, 0.0)
        workspace = model.project.workspaces[workspace_id]

        self.assertTrue(scene.command_bridge.set_node_collapsed(collapsible_id, True))
        self.assertTrue(workspace.nodes[collapsible_id].collapsed)
        self.assertFalse(scene.command_bridge.set_node_collapsed(fixed_id, True))
        self.assertFalse(workspace.nodes[fixed_id].collapsed)

    def test_canvas_batch_rewire_request_forwards_all_arguments(self) -> None:
        source = _EdgeRewireCanvasSource()
        command_bridge = GraphCanvasCommandBridge(workspace_edit_controller=source)

        self.assertTrue(
            command_bridge.request_rewire_edges(
                ["edge-a", "edge-b"], "target", "node", "port", True, True
            )
        )
        self.assertEqual(
            source.calls,
            [(["edge-a", "edge-b"], "target", "node", "port", True, True)],
        )
        self.assertLess(
            command_bridge.metaObject().indexOfMethod(
                b"request_move_edge_endpoint(QString,QString,QString,QString,bool)"
            ),
            0,
        )

    def test_mutation_history_routes_to_direct_graph_operation_boundaries(self) -> None:
        helper_text = (
            _REPO_ROOT / "ea_node_editor" / "ui_qml" / "graph_scene_mutation_history.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("class _GraphScenePropertyMutations:", helper_text)
        self.assertNotIn("class _GraphSceneGeometryMutations:", helper_text)
        self.assertNotIn("class _GraphSceneStructureMutations:", helper_text)
        self.assertNotIn("class _GraphSceneFragmentMutations:", helper_text)
        self.assertIn("class GraphSceneMutationPolicy:", helper_text)
        self.assertIn("class GraphSceneMutationHistory:", helper_text)
        self.assertIn("def set_node_property(self, node_id: str, key: str, value: Any) -> None:", helper_text)
        self.assertIn("def move_nodes_by_delta(self, node_ids: list[Any], dx: float, dy: float) -> bool:", helper_text)
        self.assertIn("def _validated_mutations(self) -> ValidatedGraphMutation:", helper_text)
        self.assertIn("def _record_mutations(self) -> GraphRecordMutation:", helper_text)
        self.assertIn("model.validated_mutations(", helper_text)
        self.assertIn("GraphRecordMutation(", helper_text)
        self.assertIn("insert_graph_fragment(", helper_text)
        self.assertNotIn("_mutation_boundary", helper_text)
        self.assertNotIn("model.mutation_service", helper_text)
        self.assertNotIn("WorkspaceMutationService", helper_text)
        self.assertIn("boundary_adapters=self._boundary_adapters", helper_text)

    def test_mutation_history_facade_uses_helper_split(self) -> None:
        ui_qml_dir = _REPO_ROOT / "ea_node_editor" / "ui_qml"
        package_root = ui_qml_dir / "graph_scene_mutation"
        facade_path = ui_qml_dir / "graph_scene_mutation_history.py"
        facade_text = facade_path.read_text(encoding="utf-8")
        policy_text = (package_root / "policy.py").read_text(encoding="utf-8")
        policy_bridge_text = (ui_qml_dir / "graph_scene" / "policy_bridge.py").read_text(encoding="utf-8")
        helper_paths = {
            "__init__.py": package_root / "__init__.py",
            "policy.py": package_root / "policy.py",
            "selection_and_scope_ops.py": package_root / "selection_and_scope_ops.py",
            "clipboard_and_fragment_ops.py": package_root / "clipboard_and_fragment_ops.py",
            "alignment_and_distribution_ops.py": package_root / "alignment_and_distribution_ops.py",
            "collision_avoidance_ops.py": package_root / "collision_avoidance_ops.py",
            "grouping_and_subnode_ops.py": package_root / "grouping_and_subnode_ops.py",
            "group_backdrop_ops.py": package_root / "group_backdrop_ops.py",
        }

        self.assertTrue(package_root.is_dir())
        for snippet in (
            "graph_scene_mutation.policy",
            "graph_scene_mutation.selection_and_scope_ops",
            "graph_scene_mutation.clipboard_and_fragment_ops",
            "graph_scene_mutation.alignment_and_distribution_ops",
            "graph_scene_mutation.collision_avoidance_ops",
            "graph_scene_mutation.grouping_and_subnode_ops",
            "graph_scene_mutation.group_backdrop_ops",
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, facade_text)
        for helper_name, helper_path in helper_paths.items():
            with self.subTest(helper=helper_name):
                self.assertTrue(helper_path.exists(), msg=f"missing helper {helper_name}")

        module = importlib.import_module("ea_node_editor.ui_qml.graph_scene_mutation_history")
        self.assertEqual(
            module.GraphSceneMutationPolicy.are_ports_compatible.__module__,
            "ea_node_editor.ui_qml.graph_scene_mutation.policy",
        )
        self.assertFalse(hasattr(module.GraphSceneMutationPolicy, "are_port_kinds_compatible"))
        self.assertFalse(hasattr(module.GraphSceneMutationPolicy, "are_data_types_compatible"))
        self.assertNotIn("def are_port_kinds_compatible", policy_text)
        self.assertNotIn("def are_data_types_compatible", policy_text)
        self.assertIn(
            "from ea_node_editor.graph.effective_ports import are_port_kinds_compatible",
            policy_bridge_text,
        )
        self.assertIn("return are_port_kinds_compatible(str(source_kind), str(target_kind))", policy_bridge_text)
        self.assertIn("return registry.data_types.compatibility(", policy_bridge_text)
        self.assertEqual(
            module.GraphSceneMutationHistory.add_node_from_type.__module__,
            "ea_node_editor.ui_qml.graph_scene_mutation.selection_and_scope_ops",
        )
        self.assertEqual(
            module.GraphSceneMutationHistory.move_node.__module__,
            "ea_node_editor.ui_qml.graph_scene_mutation.alignment_and_distribution_ops",
        )
        self.assertEqual(
            module.GraphSceneMutationHistory.expand_collision_avoidance_updates.__module__,
            "ea_node_editor.ui_qml.graph_scene_mutation.collision_avoidance_ops",
        )
        self.assertEqual(
            module.GraphSceneMutationHistory.group_selected_nodes.__module__,
            "ea_node_editor.ui_qml.graph_scene_mutation.grouping_and_subnode_ops",
        )
        self.assertEqual(
            module.GraphSceneMutationHistory.wrap_nodes_in_group_backdrop.__module__,
            "ea_node_editor.ui_qml.graph_scene_mutation.group_backdrop_ops",
        )
        self.assertEqual(
            module.GraphSceneMutationHistory.duplicate_selected_subgraph.__module__,
            "ea_node_editor.ui_qml.graph_scene_mutation.clipboard_and_fragment_ops",
        )

    def test_graph_canvas_bridges_resolve_split_scene_sources_without_losing_scene_compatibility(self) -> None:
        bridge_text = (_REPO_ROOT / "ea_node_editor" / "ui_qml" / "graph_scene_bridge.py").read_text(encoding="utf-8")
        support_text = (
            _REPO_ROOT / "ea_node_editor" / "ui_qml" / "graph_scene" / "state_support.py"
        ).read_text(encoding="utf-8")
        state_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(
                (_REPO_ROOT / "ea_node_editor" / "ui_qml" / "graph_canvas_state").glob("*.py")
            )
        )
        command_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(
                (_REPO_ROOT / "ea_node_editor" / "ui_qml" / "graph_canvas_command").glob("*.py")
            )
        )
        canvas_text = (
            _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "GraphCanvas.qml"
        ).read_text(encoding="utf-8")
        context_menus_text = (
            _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "graph_canvas" / "GraphCanvasContextMenus.qml"
        ).read_text(encoding="utf-8")
        node_delegate_text = (
            _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "graph_canvas" / "GraphCanvasNodeDelegate.qml"
        ).read_text(encoding="utf-8")
        input_layers_text = (
            _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "graph_canvas" / "GraphCanvasInputLayers.qml"
        ).read_text(encoding="utf-8")

        self.assertIn("GraphSceneBridgeBase", bridge_text)
        self.assertIn("def state_bridge(self) -> GraphSceneReadBridge:", support_text)
        self.assertIn("def command_bridge(self) -> GraphSceneCommandBridge:", support_text)
        self.assertIn("def policy_bridge(self) -> GraphScenePolicyBridge:", support_text)
        self.assertIn("def _resolve_scene_state_source(scene_bridge: object | None)", state_text)
        self.assertIn("def _resolve_scene_policy_source(scene_bridge: object | None)", state_text)
        self.assertIn("def _resolve_scene_command_source(scene_bridge: object | None)", command_text)
        self.assertIn("def _resolve_scene_policy_source(scene_bridge: object | None)", command_text)
        self.assertIn("readonly property var canvasStateBridgeRef: root.canvasStateBridge || null", canvas_text)
        self.assertIn("readonly property var canvasCommandBridgeRef: root.canvasCommandBridge || null", canvas_text)
        self.assertIn("readonly property var canvasViewBridgeRef: root._canvasViewportBridge", canvas_text)
        self.assertIn("readonly property var sceneCommandBridge: root.canvasCommandBridgeRef", canvas_text)
        self.assertIn("readonly property var sceneBridge: root.canvasStateBridgeRef", canvas_text)
        self.assertIn("readonly property var sceneStateBridge: root.canvasStateBridgeRef", canvas_text)
        self.assertIn("readonly property var graphActionBridgeRef: root.graphActionBridge || null", canvas_text)
        self.assertIn("sceneBridge: root.sceneStateBridge", canvas_text)
        self.assertIn("sceneCommandBridge: root.sceneCommandBridge", canvas_text)
        self.assertIn("graphActionBridge: root.graphActionBridge", canvas_text)
        self.assertIn("graphActionBridge: root.graphActionBridgeRef", canvas_text)
        self.assertIn("property var canvasViewBridge: null", canvas_text)
        self.assertNotIn("typeof graphCanvasViewBridge", canvas_text)
        self.assertNotIn("_legacyCanvasViewBridgeRef", canvas_text)
        self.assertNotIn("_canvasShellCommandBridgeRef", canvas_text)
        self.assertNotIn("_canvasSceneCommandBridgeRef", canvas_text)
        self.assertNotIn("_canvasViewCommandBridgeRef", canvas_text)
        self.assertNotIn("GraphCanvasRootBindings", canvas_text)
        self.assertIn("root.graphActionBridge.trigger_graph_action(actionId, payload || ({}))", context_menus_text)
        self.assertIn("graphActionBridge.trigger_graph_action(actionId, payload)", node_delegate_text)
        self.assertIn("payload.inline_title_edit = true", node_delegate_text)
        self.assertIn("property var graphActionBridge: null", input_layers_text)
        self.assertNotIn("property var shellCommandBridge", input_layers_text)
        self.assertIn('root._triggerGraphAction("delete_selection", { "edge_ids": edgeIds })', input_layers_text)
        self.assertIn('root._triggerGraphAction("navigate_scope_parent", ({}))', input_layers_text)
        self.assertIn('root._triggerGraphAction("navigate_scope_root", ({}))', input_layers_text)
        self.assertIn('root._triggerGraphAction("close_comment_peek", ({}))', input_layers_text)
        for retired_snippet in (
            "def request_wrap_selected_nodes_in_group_backdrop",
            "def request_edit_flow_edge_style",
            "def request_remove_edge",
            "def request_publish_custom_workflow_from_node",
            "def request_edit_passive_node_style",
            "def request_rename_node",
            "def request_ungroup_node",
            "def request_remove_node",
            "def request_duplicate_node",
            "def request_open_comment_peek",
        ):
            with self.subTest(retired_snippet=retired_snippet):
                self.assertNotIn(retired_snippet, command_text)

        scene = GraphSceneBridge()
        canvas_state_bridge = GraphCanvasStateBridge(scene_bridge=scene)
        canvas_command_bridge = GraphCanvasCommandBridge(scene_bridge=scene)

        self.assertIs(canvas_state_bridge.scene_bridge, scene)
        self.assertIs(canvas_state_bridge.scene_state_source, scene.state_bridge)
        self.assertIs(canvas_state_bridge.scene_policy_source, scene.policy_bridge)
        self.assertIs(canvas_command_bridge.scene_bridge, scene)
        self.assertIs(canvas_command_bridge.scene_command_source, scene.command_bridge)
        self.assertIs(canvas_command_bridge.scene_policy_source, scene.policy_bridge)
        command_meta = canvas_command_bridge.metaObject()
        for signature in (
            b"request_open_subnode_scope(QString)",
            b"request_close_comment_peek()",
            b"request_delete_selected_graph_items(QVariantList)",
            b"request_rewire_edges(QVariantList,QString,QString,QString,bool,bool)",
            b"set_node_geometry(QString,double,double,double,double)",
        ):
            with self.subTest(retained_command_signature=signature):
                self.assertGreaterEqual(command_meta.indexOfMethod(signature), 0)
        self.assertLess(
            command_meta.indexOfMethod(
                b"request_move_edge_endpoint(QString,QString,QString,QString,bool)"
            ),
            0,
        )
        for signature in (
            b"request_edit_flow_edge_style(QString)",
            b"request_remove_edge(QString)",
            b"request_publish_custom_workflow_from_node(QString)",
            b"request_edit_passive_node_style(QString)",
            b"request_remove_node(QString)",
            b"request_duplicate_node(QString)",
            b"request_wrap_selected_nodes_in_group_backdrop()",
            b"request_open_comment_peek(QString)",
        ):
            with self.subTest(retired_command_signature=signature):
                self.assertLess(command_meta.indexOfMethod(signature), 0)

    def test_graph_canvas_state_bridge_defaults_optional_filter_before_scene_binding(self) -> None:
        scene = GraphSceneBridge()
        canvas_state_bridge = GraphCanvasStateBridge(scene_bridge=scene)

        self.assertFalse(canvas_state_bridge.hide_optional_ports)

    def test_set_workspace_publishes_edge_payload_for_prebound_canvas_state_bridge(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        source = model.add_node(workspace_id, "core.constant", "Constant", 0.0, 0.0)
        target = model.add_node(workspace_id, "core.python_script", "Python Script", 260.0, 0.0)
        edge = model.add_edge(workspace_id, source.node_id, "value", target.node_id, "payload")

        scene = GraphSceneBridge()
        canvas_state_bridge = GraphCanvasStateBridge(scene_bridge=scene)
        scene_nodes_changed: list[str] = []
        scene_edges_changed: list[str] = []
        canvas_nodes_changed: list[str] = []
        canvas_edges_changed: list[str] = []
        scene.nodes_changed.connect(lambda: scene_nodes_changed.append("nodes"))
        scene.edges_changed.connect(lambda: scene_edges_changed.append("edges"))
        canvas_state_bridge.scene_nodes_changed.connect(lambda: canvas_nodes_changed.append("nodes"))
        canvas_state_bridge.scene_edges_changed.connect(lambda: canvas_edges_changed.append("edges"))

        scene.set_workspace(model, registry, workspace_id)

        self.assertEqual(scene_nodes_changed, ["nodes"])
        self.assertEqual(scene_edges_changed, ["edges"])
        self.assertEqual(canvas_nodes_changed, ["nodes"])
        self.assertEqual(canvas_edges_changed, ["edges"])
        self.assertIn(edge.edge_id, {payload["edge_id"] for payload in scene.edges_model})
        self.assertEqual(canvas_state_bridge.edges_model, scene.edges_model)

    def test_set_workspace_does_not_mutate_node_properties_or_exposed_ports(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        node = model.add_node(
            workspace_id,
            "core.logger",
            "Logger",
            0.0,
            0.0,
            properties={"message": 123},
            exposed_ports={},
        )

        original_properties = dict(node.properties)
        original_exposed = dict(node.exposed_ports)

        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)

        workspace_node = model.project.workspaces[workspace_id].nodes[node.node_id]
        self.assertEqual(workspace_node.properties, original_properties)
        self.assertEqual(workspace_node.exposed_ports, original_exposed)

    def test_set_workspace_does_not_prune_preexisting_invalid_model_edges(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        source = model.add_node(workspace_id, "core.constant", "Constant", 0.0, 0.0)
        target = model.add_node(workspace_id, "core.python_script", "Python Script", 240.0, 0.0)
        edge = model.add_edge(workspace_id, source.node_id, "value", target.node_id, "result")

        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)

        self.assertIn(edge.edge_id, model.project.workspaces[workspace_id].edges)

    def test_scene_mutations_route_through_direct_validated_mutations_with_boundary_adapters(self) -> None:
        registry = build_default_registry()
        original = GraphModel.validated_mutations
        calls: list[tuple[GraphModel, str, object, object | None]] = []

        def _spy(
            model: GraphModel,
            workspace_id: str,
            registry=None,
            boundary_adapters=None,
        ):
            calls.append((model, workspace_id, registry, boundary_adapters))
            return original(
                model,
                workspace_id=workspace_id,
                registry=registry,
                boundary_adapters=boundary_adapters,
            )

        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)

        with patch.object(GraphModel, "validated_mutations", autospec=True) as patched:
            patched.side_effect = _spy
            self.assertTrue(scene.add_node_from_type("core.constant", 0.0, 0.0))

        self.assertGreaterEqual(len(calls), 1)
        self.assertIs(calls[0][0], model)
        self.assertEqual(calls[0][1], workspace_id)
        self.assertIs(calls[0][2], registry)
        self.assertIsNotNone(calls[0][3])

    def test_scene_mutation_phase_instrumentation_records_non_negative_hooks(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)
        source_id = scene.add_node_from_type("core.constant", 0.0, 0.0)
        node_id = scene.add_node_from_type("core.python_script", 320.0, 40.0)
        scene.add_edge(source_id, "value", node_id, "payload")
        state_bridge = GraphCanvasStateBridge(scene_bridge=scene)
        scene.bind_runtime_history(RuntimeGraphHistory())
        state_bridge.force_visible_scene_models_exact()

        scene.clear_mutation_timing_samples()
        scene.set_mutation_timing_enabled(True)
        try:
            with scene.mutation_timing_scope(
                "rename_node",
                command_payload={"node_id": node_id, "title": "Renamed"},
            ):
                scene.set_node_title(node_id, "Renamed")
                state_bridge.force_visible_scene_models_exact()
        finally:
            scene.set_mutation_timing_enabled(False)

        samples = scene.mutation_timing_samples()
        self.assertEqual(len(samples), 1)
        sample = samples[0]
        self.assertEqual(sample["scenario"], "rename_node")
        self.assertEqual(sample["dirty_node_count"], 1)
        self.assertEqual(sample["dirty_edge_count"], 0)
        self.assertEqual(sample["scene_publication_paths"], ["title_payload_delta"])
        self.assertNotIn("full_rebuild", sample["scene_publication_paths"])
        self.assertEqual(sample["scene_publication_dirty_edge_count"], 0)
        node_delta = getattr(scene.state_bridge, "node_delta_payload", {})
        self.assertEqual(node_delta["kind"], "node_delta")
        self.assertEqual([payload["node_id"] for payload in node_delta["nodes"]], [node_id])
        self.assertFalse(node_delta["visibility_may_change"])
        visible_diagnostics = state_bridge.visible_scene_model_diagnostics
        self.assertGreaterEqual(visible_diagnostics["delta_update_count"], 1)
        self.assertEqual(visible_diagnostics["delta_fallback_count"], 0)
        self.assertGreaterEqual(sample["command_payload_bytes"], 0)
        self.assertGreaterEqual(sample["graph_delta_payload_bytes"], 0)
        self.assertGreaterEqual(sample["scene_payload_bytes"], 0)
        self.assertGreaterEqual(sample["first_frame_after_mutation_ms"], 0.0)
        for phase_name in (
            "command_dispatch_ms",
            "history_capture_ms",
            "history_apply_ms",
            "graph_model_mutation_ms",
            "payload_rebuild_ms",
            "scene_publish_ms",
            "visible_node_model_update_ms",
            "edge_payload_update_ms",
            "first_frame_after_mutation_ms",
        ):
            self.assertIn(phase_name, sample["phase_timings_ms"])
            self.assertGreaterEqual(sample["phase_timings_ms"][phase_name], 0.0)
        self.assertEqual(sample["phase_timings_ms"]["edge_payload_update_ms"], 0.0)

    def test_inline_enum_property_edit_publishes_targeted_property_delta(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)
        source_id = scene.add_node_from_type("core.constant", 0.0, 0.0)
        node_id = scene.add_node_from_type("io.process_run", 320.0, 40.0)
        target_id = scene.add_node_from_type("core.python_script", 640.0, 0.0)
        incoming_edge_id = scene.add_edge(source_id, "as_text", node_id, "stdin_text")
        outgoing_edge_id = scene.add_edge(node_id, "stdout", target_id, "payload")
        state_bridge = GraphCanvasStateBridge(scene_bridge=scene)
        scene.bind_runtime_history(RuntimeGraphHistory())
        state_bridge.force_visible_scene_models_exact()

        rebuild_calls: list[str] = []
        original_rebuild_models = scene._scene_context.rebuild_models

        def _unexpected_rebuild_models() -> None:
            rebuild_calls.append("rebuild")
            original_rebuild_models()

        scene.clear_mutation_timing_samples()
        scene.set_mutation_timing_enabled(True)
        scene._scene_context.rebuild_models = _unexpected_rebuild_models
        try:
            with scene.mutation_timing_scope(
                "edit_inline_enum_property",
                command_payload={"node_id": node_id, "key": "output_mode", "value": "stored"},
            ):
                scene.set_node_property(node_id, "output_mode", "stored")
                state_bridge.force_visible_scene_models_exact()
        finally:
            scene._scene_context.rebuild_models = original_rebuild_models
            scene.set_mutation_timing_enabled(False)

        self.assertEqual(rebuild_calls, [])
        sample = scene.mutation_timing_samples()[-1]
        self.assertEqual(sample["scene_publication_paths"], ["node_property_payload_delta"])
        self.assertNotIn("full_rebuild", sample["scene_publication_paths"])
        self.assertEqual(sample["scene_publication_dirty_node_count"], 1)
        self.assertEqual(sample["scene_publication_dirty_edge_count"], 2)
        node_delta = getattr(scene.state_bridge, "node_delta_payload", {})
        self.assertEqual(node_delta["kind"], "node_delta")
        self.assertEqual(node_delta["reason"], "node_property_payload_delta")
        self.assertFalse(node_delta["visibility_may_change"])
        self.assertEqual([payload["node_id"] for payload in node_delta["nodes"]], [node_id])
        payload = {item["node_id"]: item for item in scene.nodes_model}[node_id]
        inline_items = {item["key"]: item for item in payload["inline_properties"]}
        self.assertEqual(payload["properties"]["output_mode"], "stored")
        self.assertEqual(inline_items["output_mode"]["value"], "stored")
        edge_delta = scene.edge_delta_payload
        self.assertEqual(edge_delta["reason"], "node_property")
        self.assertCountEqual(edge_delta["updated_edge_ids"], [incoming_edge_id, outgoing_edge_id])
        visible_diagnostics = state_bridge.visible_scene_model_diagnostics
        self.assertGreaterEqual(visible_diagnostics["delta_update_count"], 1)
        self.assertEqual(visible_diagnostics["delta_fallback_count"], 0)

    def test_default_property_edit_publishes_targeted_delta(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)
        node_id = scene.add_node_from_type("core.logger", 320.0, 40.0)
        state_bridge = GraphCanvasStateBridge(scene_bridge=scene)
        scene.bind_runtime_history(RuntimeGraphHistory())
        state_bridge.force_visible_scene_models_exact()
        rebuild_calls: list[str] = []
        original_rebuild_models = scene._scene_context.rebuild_models

        def _unexpected_rebuild_models() -> None:
            rebuild_calls.append("rebuild")
            original_rebuild_models()

        scene.clear_mutation_timing_samples()
        scene.set_mutation_timing_enabled(True)
        scene._scene_context.rebuild_models = _unexpected_rebuild_models
        try:
            with scene.mutation_timing_scope(
                "edit_inline_text_property",
                command_payload={"node_id": node_id, "key": "message", "value": "snappy update"},
            ):
                scene.set_node_property(node_id, "message", "snappy update")
                state_bridge.force_visible_scene_models_exact()
        finally:
            scene._scene_context.rebuild_models = original_rebuild_models
            scene.set_mutation_timing_enabled(False)

        self.assertEqual(rebuild_calls, [])
        sample = scene.mutation_timing_samples()[-1]
        self.assertEqual(sample["scene_publication_paths"], ["node_property_payload_delta"])
        self.assertNotIn("full_rebuild", sample["scene_publication_paths"])
        node_delta = getattr(scene.state_bridge, "node_delta_payload", {})
        self.assertEqual(node_delta["kind"], "node_delta")
        self.assertEqual(node_delta["reason"], "node_property_payload_delta")
        self.assertFalse(node_delta["visibility_may_change"])
        payload = {item["node_id"]: item for item in scene.nodes_model}[node_id]
        ports = {item["key"]: item for item in payload["ports"]}
        self.assertEqual(payload["properties"]["message"], "snappy update")
        self.assertEqual(ports["message"]["default_property"]["value"], "snappy update")
        self.assertEqual(scene.edge_delta_payload, {})
        visible_diagnostics = state_bridge.visible_scene_model_diagnostics
        self.assertGreaterEqual(visible_diagnostics["delta_update_count"], 1)
        self.assertEqual(visible_diagnostics["delta_fallback_count"], 0)

    def test_connected_default_property_edit_preserves_edge_and_uses_targeted_delta(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)
        source_id = scene.add_node_from_type("core.constant", 0.0, 0.0)
        node_id = scene.add_node_from_type("core.logger", 320.0, 40.0)
        scene.bind_runtime_history(RuntimeGraphHistory())
        data_edge_id = scene.add_edge(source_id, "as_text", node_id, "message")
        workspace = model.project.workspaces[workspace_id]
        self.assertIn(data_edge_id, workspace.edges)

        rebuild_calls: list[str] = []
        original_rebuild_models = scene._scene_context.rebuild_models

        def _record_rebuild_models() -> None:
            rebuild_calls.append("rebuild")
            original_rebuild_models()

        scene.clear_mutation_timing_samples()
        scene.set_mutation_timing_enabled(True)
        scene._scene_context.rebuild_models = _record_rebuild_models
        try:
            with scene.mutation_timing_scope(
                "edit_property_auto_locks_port",
                command_payload={"node_id": node_id, "key": "message", "value": "manual override"},
            ):
                scene.set_node_property(node_id, "message", "manual override")
        finally:
            scene._scene_context.rebuild_models = original_rebuild_models
            scene.set_mutation_timing_enabled(False)

        self.assertEqual(rebuild_calls, [])
        self.assertIn(data_edge_id, workspace.edges)
        self.assertEqual(workspace.nodes[node_id].properties["message"], "manual override")
        sample = scene.mutation_timing_samples()[-1]
        self.assertEqual(sample["scene_publication_paths"], ["node_property_payload_delta"])
        self.assertNotIn("full_rebuild", sample["scene_publication_paths"])

    def test_port_label_edit_publishes_targeted_payload_delta(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)
        source_id = scene.add_node_from_type("core.constant", 0.0, 0.0)
        target_id = scene.add_node_from_type("core.python_script", 320.0, 40.0)
        edge_id = scene.add_edge(source_id, "value", target_id, "payload")
        state_bridge = GraphCanvasStateBridge(scene_bridge=scene)
        scene.bind_runtime_history(RuntimeGraphHistory())
        state_bridge.force_visible_scene_models_exact()

        rebuild_calls: list[str] = []
        original_rebuild_models = scene._scene_context.rebuild_models

        def _unexpected_rebuild_models() -> None:
            rebuild_calls.append("rebuild")
            original_rebuild_models()

        scene.clear_mutation_timing_samples()
        scene.set_mutation_timing_enabled(True)
        scene._scene_context.rebuild_models = _unexpected_rebuild_models
        try:
            with scene.mutation_timing_scope(
                "edit_port_label",
                command_payload={"node_id": source_id, "port_key": "value", "label": "Input Value"},
            ):
                scene.set_node_port_label(source_id, "value", "Input Value")
                state_bridge.force_visible_scene_models_exact()
        finally:
            scene._scene_context.rebuild_models = original_rebuild_models
            scene.set_mutation_timing_enabled(False)

        self.assertEqual(rebuild_calls, [])
        sample = scene.mutation_timing_samples()[-1]
        self.assertEqual(sample["scene_publication_paths"], ["port_label_payload_delta"])
        self.assertNotIn("full_rebuild", sample["scene_publication_paths"])
        self.assertEqual(sample["scene_publication_dirty_node_count"], 1)
        self.assertEqual(sample["scene_publication_dirty_edge_count"], 1)
        node_delta = getattr(scene.state_bridge, "node_delta_payload", {})
        self.assertEqual(node_delta["kind"], "node_delta")
        self.assertEqual(node_delta["reason"], "port_label_payload_delta")
        self.assertFalse(node_delta["visibility_may_change"])
        self.assertEqual([payload["node_id"] for payload in node_delta["nodes"]], [source_id])
        payload = {item["node_id"]: item for item in scene.nodes_model}[source_id]
        ports = {item["key"]: item for item in payload["ports"]}
        self.assertEqual(ports["value"]["label"], "Input Value")
        edge_delta = scene.edge_delta_payload
        self.assertEqual(edge_delta["reason"], "port_label")
        self.assertEqual(edge_delta["updated_edge_ids"], [edge_id])
        visible_diagnostics = state_bridge.visible_scene_model_diagnostics
        self.assertGreaterEqual(visible_diagnostics["delta_update_count"], 1)
        self.assertEqual(visible_diagnostics["delta_fallback_count"], 0)

    def test_scene_rename_history_reuses_two_snapshots(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)
        node_id = scene.add_node_from_type("core.logger", 120.0, 40.0)
        history = _CountingRuntimeGraphHistory()
        scene.bind_runtime_history(history)

        scene.set_node_title(node_id, "Renamed")

        self.assertEqual(history.capture_count, 2)
        self.assertEqual(history.undo_depth(workspace_id), 1)
        self.assertEqual(history._undo_stacks[workspace_id][-1].action_type, ACTION_RENAME_NODE)

    def test_scene_grouped_move_history_reuses_two_snapshots(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)
        first_id = scene.add_node_from_type("core.logger", 120.0, 40.0)
        second_id = scene.add_node_from_type("core.constant", 360.0, 40.0)
        history = _CountingRuntimeGraphHistory()
        scene.bind_runtime_history(history)

        self.assertTrue(scene.move_nodes_by_delta([first_id, second_id], 40.0, 20.0))

        self.assertEqual(history.capture_count, 2)
        self.assertEqual(history.undo_depth(workspace_id), 1)
        self.assertEqual(history._undo_stacks[workspace_id][-1].action_type, ACTION_MOVE_NODE)

    def test_scene_grouped_move_noop_skips_after_snapshot(self) -> None:
        class _HiddenNodeDict(dict):
            def __init__(self, source: dict, hidden_node_id: str) -> None:
                super().__init__(source)
                self._hidden_node_id = hidden_node_id
                self._visible_gets_remaining = 1

            def get(self, key, default=None):  # noqa: ANN001
                if str(key) == self._hidden_node_id:
                    if self._visible_gets_remaining > 0:
                        self._visible_gets_remaining -= 1
                        return super().get(key, default)
                    return default
                return super().get(key, default)

        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)
        node_id = scene.add_node_from_type("core.logger", 120.0, 40.0)
        history = _CountingRuntimeGraphHistory()
        scene.bind_runtime_history(history)
        workspace = model.project.workspaces[workspace_id]
        original_nodes = workspace.nodes
        workspace.nodes = _HiddenNodeDict(original_nodes, node_id)
        try:
            self.assertFalse(scene.move_nodes_by_delta([node_id], 40.0, 20.0))
        finally:
            workspace.nodes = original_nodes

        self.assertEqual(history.capture_count, 1)
        self.assertEqual(history.undo_depth(workspace_id), 0)

    def test_node_expand_collapse_publishes_targeted_geometry_delta(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        preferences = _ExpandCollisionPreferenceSource({"enabled": False})
        scene = GraphSceneBridge()
        scene.bind_graphics_preferences_source(preferences)
        scene.set_workspace(model, registry, workspace_id)
        source_id = scene.add_node_from_type("core.constant", 0.0, 0.0)
        node_id = scene.add_node_from_type("core.python_script", 320.0, 40.0)
        target_id = scene.add_node_from_type("core.trigger", 640.0, 0.0)
        incoming_edge_id = scene.add_edge(source_id, "value", node_id, "payload")
        outgoing_edge_id = scene.add_edge(node_id, "result", target_id, "input")
        history = _CountingRuntimeGraphHistory()
        scene.bind_runtime_history(history)
        state_bridge = GraphCanvasStateBridge(scene_bridge=scene)
        state_bridge.force_visible_scene_models_exact()

        def _sample_toggle(collapsed: bool) -> dict[str, object]:
            scene.clear_mutation_timing_samples()
            scene.set_mutation_timing_enabled(True)
            try:
                with scene.mutation_timing_scope(
                    "toggle_collapsed",
                    command_payload={"node_id": node_id, "collapsed": collapsed},
                ):
                    scene.set_node_collapsed(node_id, collapsed)
                    state_bridge.force_visible_scene_models_exact()
                return scene.mutation_timing_samples()[-1]
            finally:
                scene.set_mutation_timing_enabled(False)

        collapse_sample = _sample_toggle(True)

        self.assertEqual(history.capture_count, 2)
        self.assertEqual(collapse_sample["scene_publication_paths"], ["node_collapsed_geometry_delta"])
        self.assertNotIn("full_rebuild", collapse_sample["scene_publication_paths"])
        self.assertEqual(collapse_sample["dirty_node_count"], 1)
        self.assertEqual(collapse_sample["dirty_edge_count"], 2)
        self.assertEqual(collapse_sample["scene_publication_dirty_node_count"], 1)
        self.assertEqual(collapse_sample["scene_publication_dirty_edge_count"], 2)
        node_delta = getattr(scene.state_bridge, "node_delta_payload", {})
        self.assertEqual(node_delta["kind"], "node_delta")
        self.assertEqual(node_delta["reason"], "node_collapsed_geometry_delta")
        self.assertTrue(node_delta["visibility_may_change"])
        self.assertEqual([payload["node_id"] for payload in node_delta["nodes"]], [node_id])
        self.assertTrue(node_delta["nodes"][0]["collapsed"])
        edge_delta = scene.edge_delta_payload
        self.assertEqual(edge_delta["reason"], "node_geometry")
        self.assertCountEqual(edge_delta["updated_edge_ids"], [incoming_edge_id, outgoing_edge_id])
        collapsed_payload = {payload["node_id"]: payload for payload in scene.nodes_model}[node_id]
        self.assertTrue(collapsed_payload["collapsed"])

        expand_sample = _sample_toggle(False)

        self.assertEqual(history.capture_count, 4)
        self.assertEqual(expand_sample["scene_publication_paths"], ["node_collapsed_geometry_delta"])
        self.assertNotIn("full_rebuild", expand_sample["scene_publication_paths"])
        self.assertEqual(expand_sample["dirty_node_count"], 1)
        self.assertEqual(expand_sample["dirty_edge_count"], 2)
        node_delta = getattr(scene.state_bridge, "node_delta_payload", {})
        self.assertEqual([payload["node_id"] for payload in node_delta["nodes"]], [node_id])
        self.assertFalse(node_delta["nodes"][0]["collapsed"])
        edge_delta = scene.edge_delta_payload
        self.assertCountEqual(edge_delta["updated_edge_ids"], [incoming_edge_id, outgoing_edge_id])
        expanded_payload = {payload["node_id"]: payload for payload in scene.nodes_model}[node_id]
        self.assertFalse(expanded_payload["collapsed"])

    def test_edge_mutations_publish_delta_payload_metrics(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)
        source_id = scene.add_node_from_type("core.constant", 0.0, 0.0)
        logger_id = scene.add_node_from_type("core.python_script", 320.0, 40.0)
        end_id = scene.add_node_from_type("core.trigger", 640.0, 0.0)
        state_bridge = GraphCanvasStateBridge(scene_bridge=scene)
        scene.bind_runtime_history(RuntimeGraphHistory())
        state_bridge.force_visible_scene_models_exact()
        self.assertEqual(len(scene.nodes_model), 3)

        def _sample_for(scenario: str, callback):
            scene.clear_mutation_timing_samples()
            scene.set_mutation_timing_enabled(True)
            try:
                with scene.mutation_timing_scope(scenario, command_payload={"scenario": scenario}):
                    result = callback()
                    delta_payload = copy.deepcopy(scene.edge_delta_payload)
                    state_bridge.force_visible_scene_models_exact()
                return result, scene.mutation_timing_samples()[-1], delta_payload
            finally:
                scene.set_mutation_timing_enabled(False)

        edge_id, add_sample, add_delta = _sample_for(
            "create_edge",
            lambda: scene.add_edge(source_id, "value", logger_id, "payload"),
        )

        self.assertEqual(add_sample["dirty_node_count"], 2)
        self.assertEqual(add_sample["dirty_edge_count"], 1)
        self.assertGreater(add_sample["graph_delta_payload_bytes"], 0)
        self.assertGreater(add_sample["scene_payload_bytes"], 0)
        self.assertEqual(add_delta["added_edge_ids"], [edge_id])
        self.assertEqual(add_delta["dirty_edge_ids"], [edge_id])
        self.assertCountEqual(add_delta["dirty_node_ids"], [source_id, logger_id])
        self.assertEqual(add_delta["schema"], "graph_scene_edge_structural_delta")
        self.assertEqual(add_delta["version"], 1)
        self.assertFalse(add_delta["requires_full_refresh"])
        self.assertEqual(add_delta["reason"], "edge_topology")
        self.assertEqual(add_delta["edge_count_after"], 1)
        self.assertCountEqual(add_delta["affected_node_ids"], [source_id, logger_id])
        self.assertEqual(len(add_delta["added_edges"]), 1)
        added_entry = add_delta["added_edges"][0]
        self.assertEqual(added_entry["edge_id"], edge_id)
        self.assertEqual(added_entry["index"], 0)
        self.assertEqual(added_entry["payload"]["edge_id"], edge_id)
        self.assertEqual(added_entry["payload"]["source_node_id"], source_id)
        self.assertEqual(added_entry["payload"]["target_node_id"], logger_id)
        self.assertEqual(state_bridge.edge_delta_payload["sequence"], add_delta["sequence"])

        _, remove_sample, remove_delta = _sample_for("remove_edge", lambda: scene.remove_edge(edge_id))

        self.assertEqual(remove_sample["dirty_node_count"], 2)
        self.assertEqual(remove_sample["dirty_edge_count"], 1)
        self.assertGreater(remove_sample["graph_delta_payload_bytes"], 0)
        self.assertEqual(remove_delta["removed_edge_ids"], [edge_id])
        self.assertGreater(remove_delta["sequence"], add_delta["sequence"])
        self.assertEqual(remove_delta["removed_edges"], [{"edge_id": edge_id}])
        self.assertEqual(remove_delta["edge_count_after"], 0)
        self.assertFalse(remove_delta["requires_full_refresh"])
        self.assertCountEqual(remove_delta["affected_node_ids"], [source_id, logger_id])
        self.assertNotIn(edge_id, {item["edge_id"] for item in scene.edges_model})

        first_incident = scene.add_edge(source_id, "value", logger_id, "payload")
        second_incident = scene.add_edge(logger_id, "result", end_id, "input")
        _, delete_sample, delete_delta = _sample_for("delete_node", lambda: scene.remove_node(logger_id))

        self.assertEqual(delete_sample["dirty_node_count"], 3)
        self.assertEqual(delete_sample["dirty_edge_count"], 2)
        self.assertGreater(delete_delta["sequence"], remove_delta["sequence"])
        self.assertCountEqual(delete_delta["removed_edge_ids"], [first_incident, second_incident])
        self.assertCountEqual(
            [item["edge_id"] for item in delete_delta["removed_edges"]],
            [first_incident, second_incident],
        )
        self.assertCountEqual(delete_delta["removed_node_ids"], [logger_id])
        self.assertCountEqual(delete_delta["affected_node_ids"], [source_id, logger_id, end_id])
        self.assertEqual(delete_delta["edge_count_after"], 0)
        self.assertNotIn(logger_id, {item["node_id"] for item in scene.nodes_model})
        self.assertFalse({first_incident, second_incident} & {item["edge_id"] for item in scene.edges_model})

    def test_node_position_delta_reuses_cached_edge_payloads_without_full_edge_builder(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)
        source_id = scene.add_node_from_type("core.constant", 0.0, 0.0)
        logger_id = scene.add_node_from_type("core.python_script", 320.0, 40.0)
        edge_id = scene.add_edge(source_id, "value", logger_id, "payload")
        scene.bind_runtime_history(RuntimeGraphHistory())
        self.assertIn(edge_id, {payload["edge_id"] for payload in scene.edges_model})

        original_builder = scene._scene_context._payload_builder.build_edge_payloads_for_ids

        def _unexpected_edge_builder(**_kwargs):  # noqa: ANN003
            raise AssertionError("node position deltas should reuse cached edge payloads")

        scene._scene_context._payload_builder.build_edge_payloads_for_ids = _unexpected_edge_builder
        try:
            scene.move_node(source_id, 80.0, 40.0)
        finally:
            scene._scene_context._payload_builder.build_edge_payloads_for_ids = original_builder

        delta = scene.edge_delta_payload
        self.assertEqual(delta["reason"], "node_position")
        self.assertIn(edge_id, delta["updated_edge_ids"])
        self.assertEqual([entry["edge_id"] for entry in delta["updated_edges"]], [edge_id])

    def test_edge_add_delta_uses_cached_edge_payload_fast_path_for_normal_scope(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)
        source_id = scene.add_node_from_type("core.constant", 0.0, 0.0)
        logger_id = scene.add_node_from_type("core.python_script", 320.0, 40.0)
        self.assertEqual(len(scene.nodes_model), 2)
        self.assertEqual(scene.edges_model, [])

        original_builder = scene._scene_context._payload_builder.build_edge_payloads_for_ids

        def _unexpected_edge_builder(**_kwargs):  # noqa: ANN003
            raise AssertionError("normal edge add should use cached edge payload fast path")

        scene._scene_context._payload_builder.build_edge_payloads_for_ids = _unexpected_edge_builder
        try:
            edge_id = scene.add_edge(source_id, "value", logger_id, "payload")
        finally:
            scene._scene_context._payload_builder.build_edge_payloads_for_ids = original_builder

        delta = scene.edge_delta_payload
        self.assertEqual(delta["reason"], "edge_topology")
        self.assertEqual(delta["added_edge_ids"], [edge_id])
        self.assertEqual([entry["edge_id"] for entry in delta["added_edges"]], [edge_id])
        self.assertEqual([payload["edge_id"] for payload in scene.edges_model], [edge_id])

    def test_edge_add_undo_redo_refreshes_structural_delta_without_rebuild(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)
        source_id = scene.add_node_from_type("core.constant", 0.0, 0.0)
        logger_id = scene.add_node_from_type("core.python_script", 320.0, 40.0)
        history = RuntimeGraphHistory()
        scene.bind_runtime_history(history)
        history.clear_workspace(workspace_id)
        workspace = model.project.workspaces[workspace_id]
        nodes_changed: list[str] = []
        edges_changed: list[str] = []
        scene.nodes_changed.connect(lambda: nodes_changed.append("nodes"))
        scene.edges_changed.connect(lambda: edges_changed.append("edges"))

        edge_id = scene.add_edge(source_id, "value", logger_id, "payload")
        self.assertEqual(history.undo_depth(workspace_id), 1)
        self.assertEqual(history._undo_stacks[workspace_id][-1].action_type, ACTION_ADD_EDGE)

        rebuild_calls: list[str] = []
        original_rebuild_models = scene._scene_context.rebuild_models

        def _unexpected_rebuild_models() -> None:
            rebuild_calls.append("rebuild")
            original_rebuild_models()

        scene._scene_context.rebuild_models = _unexpected_rebuild_models
        try:
            self.assertIsNotNone(history.undo_workspace(workspace_id, workspace))
            scene.refresh_workspace_from_model(workspace_id)
            undo_delta = copy.deepcopy(scene.edge_delta_payload)

            self.assertIsNotNone(history.redo_workspace(workspace_id, workspace))
            scene.refresh_workspace_from_model(workspace_id)
            redo_delta = copy.deepcopy(scene.edge_delta_payload)
        finally:
            scene._scene_context.rebuild_models = original_rebuild_models

        self.assertEqual(rebuild_calls, [])
        self.assertEqual(undo_delta["reason"], "edge_topology")
        self.assertEqual(undo_delta["removed_edge_ids"], [edge_id])
        self.assertEqual(undo_delta["removed_edges"], [{"edge_id": edge_id}])
        self.assertEqual(undo_delta["edge_count_after"], 0)
        self.assertFalse(undo_delta["requires_full_refresh"])
        self.assertEqual(redo_delta["reason"], "edge_topology")
        self.assertEqual(redo_delta["added_edge_ids"], [edge_id])
        self.assertEqual(redo_delta["dirty_edge_ids"], [edge_id])
        self.assertEqual(redo_delta["edge_count_after"], 1)
        self.assertFalse(redo_delta["requires_full_refresh"])
        self.assertEqual(nodes_changed, ["nodes", "nodes", "nodes"])
        self.assertEqual(edges_changed, ["edges", "edges", "edges"])

    def test_group_selected_nodes_delegates_to_direct_graph_grouping_operation(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)
        node_a = scene.add_node_from_type("core.constant", 0.0, 0.0)
        node_b = scene.add_node_from_type("core.logger", 240.0, 80.0)
        scene.select_node(node_a, False)
        scene.select_node(node_b, True)

        from ea_node_editor.ui_qml.graph_scene_mutation import grouping_and_subnode_ops

        def _spy(
            *,
            model: GraphModel,
            registry,
            workspace_id: str,
            selected_node_ids: list[object],
            scope_path: tuple[object, ...],
            shell_x: float,
            shell_y: float,
        ):
            calls.append((workspace_id, {str(node_id) for node_id in selected_node_ids}, tuple(scope_path)))
            return original(
                model=model,
                registry=registry,
                workspace_id=workspace_id,
                selected_node_ids=selected_node_ids,
                scope_path=scope_path,
                shell_x=shell_x,
                shell_y=shell_y,
            )

        original = grouping_and_subnode_ops.group_selection_into_subnode
        calls: list[tuple[str, set[str], tuple[str, ...]]] = []
        with patch.object(grouping_and_subnode_ops, "group_selection_into_subnode") as patched:
            patched.side_effect = _spy
            self.assertTrue(scene.group_selected_nodes())

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], workspace_id)
        self.assertEqual(calls[0][1], {node_a, node_b})
        self.assertEqual(calls[0][2], ())

    def test_fragment_rewrites_delegate_to_direct_graph_fragment_operation(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)
        source_id = scene.add_node_from_type("core.constant", 0.0, 0.0)
        target_id = scene.add_node_from_type("core.python_script", 240.0, 80.0)
        scene.add_edge(source_id, "value", target_id, "payload")
        scene.select_node(source_id, False)
        scene.select_node(target_id, True)
        fragment = scene.serialize_selected_subgraph_fragment()
        self.assertIsNotNone(fragment)
        assert fragment is not None

        import ea_node_editor.ui_qml.graph_scene_mutation_history as mutation_history

        original = mutation_history.insert_graph_fragment
        calls: list[tuple[str, int, int, float, float]] = []

        def _spy(
            *,
            model: GraphModel,
            registry,
            workspace_id: str,
            fragment_payload: dict[str, object],
            delta_x: float,
            delta_y: float,
        ):
            calls.append(
                (
                    workspace_id,
                    len(fragment_payload["nodes"]),
                    len(fragment_payload["edges"]),
                    float(delta_x),
                    float(delta_y),
                )
            )
            return original(
                model=model,
                registry=registry,
                workspace_id=workspace_id,
                fragment_payload=fragment_payload,
                delta_x=delta_x,
                delta_y=delta_y,
            )

        with patch.object(mutation_history, "insert_graph_fragment") as patched:
            patched.side_effect = _spy
            self.assertTrue(scene.duplicate_selected_subgraph())
            self.assertTrue(scene.paste_subgraph_fragment(fragment, 620.0, 240.0))

        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][:3], (workspace_id, 2, 1))
        self.assertEqual(calls[0][3:], (40.0, 40.0))
        self.assertEqual(calls[1][:3], (workspace_id, 2, 1))

    def test_ungroup_selected_subnode_delegates_to_direct_graph_grouping_operation(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)
        node_a = scene.add_node_from_type("core.constant", 0.0, 0.0)
        node_b = scene.add_node_from_type("core.logger", 240.0, 80.0)
        scene.select_node(node_a, False)
        scene.select_node(node_b, True)
        self.assertTrue(scene.group_selected_nodes())
        shell_id = scene.selected_node_id()
        self.assertTrue(shell_id)

        from ea_node_editor.ui_qml.graph_scene_mutation import grouping_and_subnode_ops

        original = grouping_and_subnode_ops.ungroup_subnode
        calls: list[tuple[str, str]] = []

        def _spy(
            *,
            model: GraphModel,
            workspace_id: str,
            shell_node_id: str,
        ):
            calls.append((workspace_id, str(shell_node_id)))
            return original(model=model, workspace_id=workspace_id, shell_node_id=shell_node_id)

        with patch.object(grouping_and_subnode_ops, "ungroup_subnode") as patched:
            patched.side_effect = _spy
            self.assertTrue(scene.ungroup_selected_subnode())

        self.assertEqual(calls, [(workspace_id, str(shell_id))])

    def test_expand_collision_avoidance_moves_nearby_objects_in_toggle_history_group(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)
        history = RuntimeGraphHistory()
        scene.bind_runtime_history(history)

        backdrop_id = scene.add_node_from_type(GROUP_BACKDROP_TYPE_ID, 100.0, 100.0)
        scene.set_node_geometry(backdrop_id, 100.0, 100.0, 420.0, 260.0)
        inner_id = scene.add_node_from_type(LOGGER_TYPE_ID, 160.0, 160.0)
        blocker_id = scene.add_node_from_type(LOGGER_TYPE_ID, 470.0, 180.0)
        scene.set_node_collapsed(backdrop_id, True)
        history.clear_workspace(workspace_id)

        workspace = model.project.workspaces[workspace_id]
        inner_before = (float(workspace.nodes[inner_id].x), float(workspace.nodes[inner_id].y))
        blocker_before = (float(workspace.nodes[blocker_id].x), float(workspace.nodes[blocker_id].y))

        scene.set_node_collapsed(backdrop_id, False)

        self.assertFalse(workspace.nodes[backdrop_id].collapsed)
        self.assertEqual(history.undo_depth(workspace_id), 1)
        self.assertAlmostEqual(float(workspace.nodes[backdrop_id].x), 100.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[backdrop_id].y), 100.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[inner_id].x), inner_before[0], places=6)
        self.assertAlmostEqual(float(workspace.nodes[inner_id].y), inner_before[1], places=6)
        self.assertGreater(float(workspace.nodes[blocker_id].x), blocker_before[0] + 10.0)

        blocker_after_expand = (float(workspace.nodes[blocker_id].x), float(workspace.nodes[blocker_id].y))
        self.assertIsNotNone(history.undo_workspace(workspace_id, workspace))
        scene.refresh_workspace_from_model(workspace_id)
        self.assertTrue(workspace.nodes[backdrop_id].collapsed)
        self.assertAlmostEqual(float(workspace.nodes[blocker_id].x), blocker_before[0], places=6)
        self.assertAlmostEqual(float(workspace.nodes[blocker_id].y), blocker_before[1], places=6)

        self.assertIsNotNone(history.redo_workspace(workspace_id, workspace))
        scene.refresh_workspace_from_model(workspace_id)
        self.assertFalse(workspace.nodes[backdrop_id].collapsed)
        self.assertAlmostEqual(float(workspace.nodes[blocker_id].x), blocker_after_expand[0], places=6)
        self.assertAlmostEqual(float(workspace.nodes[blocker_id].y), blocker_after_expand[1], places=6)

        scene.set_node_collapsed(backdrop_id, True)
        self.assertTrue(workspace.nodes[backdrop_id].collapsed)
        self.assertAlmostEqual(float(workspace.nodes[blocker_id].x), blocker_after_expand[0], places=6)
        self.assertAlmostEqual(float(workspace.nodes[blocker_id].y), blocker_after_expand[1], places=6)

    def test_expand_collision_avoidance_respects_disabled_preference(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        preferences = _ExpandCollisionPreferenceSource({"enabled": False})
        scene = GraphSceneBridge()
        scene.bind_graphics_preferences_source(preferences)
        scene.set_workspace(model, registry, workspace_id)

        expanding_id = scene.add_node_from_type(LOGGER_TYPE_ID, 100.0, 100.0)
        blocker_id = scene.add_node_from_type(LOGGER_TYPE_ID, 240.0, 100.0)
        scene.set_node_collapsed(expanding_id, True)
        workspace = model.project.workspaces[workspace_id]
        blocker_before = (float(workspace.nodes[blocker_id].x), float(workspace.nodes[blocker_id].y))

        scene.set_node_collapsed(expanding_id, False)

        self.assertFalse(workspace.nodes[expanding_id].collapsed)
        self.assertAlmostEqual(float(workspace.nodes[blocker_id].x), blocker_before[0], places=6)
        self.assertAlmostEqual(float(workspace.nodes[blocker_id].y), blocker_before[1], places=6)

    def test_expand_collision_avoidance_reach_setting_controls_chain_displacement(self) -> None:
        local_workspace = self._expand_collision_reach_workspace(
            {
                "enabled": True,
                "strategy": "nearest",
                "scope": "all_movable",
                "radius_mode": "local",
                "local_radius_preset": "small",
                "gap_preset": "normal",
                "animate": False,
            }
        )
        unbounded_workspace = self._expand_collision_reach_workspace(
            {
                "enabled": True,
                "strategy": "nearest",
                "scope": "all_movable",
                "radius_mode": "unbounded",
                "local_radius_preset": "small",
                "gap_preset": "normal",
                "animate": False,
            }
        )

        self.assertAlmostEqual(float(local_workspace["far_after_x"]), float(local_workspace["far_before_x"]), places=6)
        self.assertAlmostEqual(float(local_workspace["far_after_y"]), float(local_workspace["far_before_y"]), places=6)
        unbounded_displacement = abs(
            float(unbounded_workspace["far_after_x"])
            - float(unbounded_workspace["far_before_x"])
        ) + abs(
            float(unbounded_workspace["far_after_y"])
            - float(unbounded_workspace["far_before_y"])
        )
        self.assertGreater(unbounded_displacement, 10.0)

    def _expand_collision_reach_workspace(self, settings: dict[str, object]) -> dict[str, float]:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        preferences = _ExpandCollisionPreferenceSource(settings)
        scene = GraphSceneBridge()
        scene.bind_graphics_preferences_source(preferences)
        scene.set_workspace(model, registry, workspace_id)

        expanding_id = scene.add_node_from_type(GROUP_BACKDROP_TYPE_ID, 100.0, 100.0)
        scene.set_node_geometry(expanding_id, 100.0, 100.0, 420.0, 260.0)
        wide_blocker_id = scene.add_node_from_type(GROUP_BACKDROP_TYPE_ID, 470.0, 180.0)
        scene.set_node_geometry(wide_blocker_id, 470.0, 180.0, 700.0, 180.0)
        far_blocker_id = scene.add_node_from_type(LOGGER_TYPE_ID, 1100.0, 200.0)
        scene.set_node_collapsed(expanding_id, True)

        workspace = model.project.workspaces[workspace_id]
        far_before_x = float(workspace.nodes[far_blocker_id].x)
        far_before_y = float(workspace.nodes[far_blocker_id].y)
        scene.set_node_collapsed(expanding_id, False)

        return {
            "far_before_x": far_before_x,
            "far_before_y": far_before_y,
            "far_after_x": float(workspace.nodes[far_blocker_id].x),
            "far_after_y": float(workspace.nodes[far_blocker_id].y),
        }


if __name__ == "__main__":
    unittest.main()
