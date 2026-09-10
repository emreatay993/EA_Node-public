from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QFontMetricsF
from PyQt6.QtWidgets import QApplication

from ea_node_editor.graph.hierarchy import subtree_node_ids
from ea_node_editor.graph.record_payloads import node_instance_from_mapping, node_instance_to_mapping
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.decorators import node_type
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.nodes.node_specs import (
    PortSpec,
    SettingsGroupItemSpec,
    SettingsGroupSpec,
)
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.runtime_contracts import (
    BOOLEAN_DATA_TYPE_ID,
    DOUBLE_DATA_TYPE_ID,
    GRAPH_DATA_TYPE_ID,
    STRING_DATA_TYPE_ID,
)
from ea_node_editor.ui.graph_interactions import GraphInteractions
from ea_node_editor.ui.shell.runtime_history import (
    ACTION_ADD_EDGE,
    ACTION_ADD_NODE,
    ACTION_DUPLICATE_SUBGRAPH,
    ACTION_EDIT_EDGE_LABEL,
    ACTION_EDIT_EDGE_STYLE,
    ACTION_EDIT_NODE_COMMENT,
    ACTION_EDIT_NODE_PROPERTY,
    ACTION_EDIT_NODE_STYLE,
    ACTION_EDIT_PORT_LABEL,
    ACTION_GROUP_SELECTED_NODES,
    ACTION_MOVE_NODE,
    ACTION_PASTE_SUBGRAPH,
    ACTION_REMOVE_EDGE,
    ACTION_REMOVE_NODE,
    ACTION_RENAME_NODE,
    ACTION_RESIZE_NODE,
    ACTION_TOGGLE_COLLAPSED,
    ACTION_TOGGLE_EXPOSED_PORT,
    ACTION_TOGGLE_SETTINGS_GROUP,
    ACTION_UNGROUP_SELECTED_SUBNODE,
    ACTION_WRAP_GROUP,
    RuntimeGraphHistory,
)
from ea_node_editor.settings import DEFAULT_GRAPH_LABEL_PIXEL_SIZE
from ea_node_editor.ui_qml.graph_geometry.standard_metrics import (
    _estimate_standard_text_width,
    standard_inline_property_pixel_size,
    standard_node_title_pixel_size,
)
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge
from tests.graph_track_b.theme_support import (
    GRAPH_STITCH_DARK_EDGE_TOKENS_V1,
    GRAPH_STITCH_LIGHT_EDGE_TOKENS_V1,
    GraphThemeBridge,
    resolve_graph_theme,
)


class _GraphLabelSizeHost(QObject):
    graphics_preferences_changed = pyqtSignal()

    @pyqtProperty(int, notify=graphics_preferences_changed)
    def graphics_graph_label_pixel_size(self) -> int:
        return 16


@node_type(
    type_id="tests.track_b_flowchart_decision",
    display_name="Decision",
    category_path=("Tests",),
    icon="branch",
    ports=(
        PortSpec("top", "neutral", "flow", "flow", side="top", allow_multiple_connections=True),
        PortSpec("right", "neutral", "flow", "flow", side="right", allow_multiple_connections=True),
        PortSpec("bottom", "neutral", "flow", "flow", side="bottom", allow_multiple_connections=True),
        PortSpec("left", "neutral", "flow", "flow", side="left", allow_multiple_connections=True),
    ),
    properties=(),
    runtime_behavior="passive",
    surface_family="flowchart",
    surface_variant="decision",
)
class _TrackBFlowchartDecisionNode:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={})

@node_type(
    type_id="tests.track_b_flowchart_connector",
    display_name="Connector",
    category_path=("Tests",),
    icon="circle",
    ports=(
        PortSpec("top", "neutral", "flow", "flow", side="top", allow_multiple_connections=True),
        PortSpec("right", "neutral", "flow", "flow", side="right", allow_multiple_connections=True),
        PortSpec("bottom", "neutral", "flow", "flow", side="bottom", allow_multiple_connections=True),
        PortSpec("left", "neutral", "flow", "flow", side="left", allow_multiple_connections=True),
    ),
    properties=(),
    runtime_behavior="passive",
    surface_family="flowchart",
    surface_variant="connector",
)
class _TrackBFlowchartConnectorNode:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={})


@node_type(
    type_id="tests.track_b_flowchart_passthrough",
    display_name="Passthrough",
    category_path=("Tests",),
    icon="route",
    ports=(
        PortSpec("left", "in", "flow", "flow", allow_multiple_connections=True),
        PortSpec("right", "out", "flow", "flow", allow_multiple_connections=True),
    ),
    properties=(),
    runtime_behavior="active",
    surface_family="flowchart",
    surface_variant="process",
)
class _TrackBFlowchartPassthroughNode:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={})


@node_type(
    type_id="tests.track_b_settings_groups",
    display_name="Settings Groups",
    category_path=("Tests",),
    icon="sliders",
    ports=(
        PortSpec(
            "width",
            "in",
            "data",
            DOUBLE_DATA_TYPE_ID,
            label="Width",
            required=False,
        ),
        PortSpec(
            "height",
            "in",
            "data",
            DOUBLE_DATA_TYPE_ID,
            label="Height",
            required=False,
        ),
        PortSpec(
            "image",
            "out",
            "data",
            GRAPH_DATA_TYPE_ID,
            label="Image",
        ),
    ),
    properties=(),
    settings_groups=(
        SettingsGroupSpec(
            group_id="general",
            label="General Options",
            items=(SettingsGroupItemSpec(port_key="width"),),
        ),
        SettingsGroupSpec(
            group_id="plot",
            label="Signal plot options",
            items=(SettingsGroupItemSpec(port_key="height"),),
        ),
    ),
    runtime_behavior="active",
)
class _TrackBSettingsGroupsNode:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={"image": None})


class _GraphCanvasPreferenceBridge(QObject):
    graphics_preferences_changed = pyqtSignal()
    snap_to_grid_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._graphics_show_grid = True
        self._graphics_grid_style = "lines"
        self._graphics_show_minimap = True
        self._graphics_minimap_expanded = True
        self._graphics_show_port_labels = True
        self._graphics_graph_label_pixel_size = 10
        self._graphics_node_title_icon_pixel_size = 10
        self._graphics_lightweight_canvas = False
        self._snap_to_grid_enabled = False
        self.minimap_update_history: list[bool] = []

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_show_grid(self) -> bool:
        return bool(self._graphics_show_grid)

    @pyqtProperty(str, notify=graphics_preferences_changed)
    def graphics_grid_style(self) -> str:
        return str(self._graphics_grid_style)

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_show_minimap(self) -> bool:
        return bool(self._graphics_show_minimap)

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_minimap_expanded(self) -> bool:
        return bool(self._graphics_minimap_expanded)

    @pyqtProperty(bool, notify=snap_to_grid_changed)
    def snap_to_grid_enabled(self) -> bool:
        return bool(self._snap_to_grid_enabled)

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_show_port_labels(self) -> bool:
        return bool(self._graphics_show_port_labels)

    @pyqtProperty(int, notify=graphics_preferences_changed)
    def graphics_graph_label_pixel_size(self) -> int:
        return int(self._graphics_graph_label_pixel_size)

    @pyqtProperty(int, notify=graphics_preferences_changed)
    def graphics_node_title_icon_pixel_size(self) -> int:
        return int(self._graphics_node_title_icon_pixel_size)

    @pyqtProperty(bool, notify=graphics_preferences_changed)
    def graphics_lightweight_canvas(self) -> bool:
        return bool(self._graphics_lightweight_canvas)

    @pyqtProperty(float, constant=True)
    def snap_grid_size(self) -> float:
        return 20.0

    def set_graphics_show_port_labels_value(self, value: bool) -> None:
        normalized = bool(value)
        if self._graphics_show_port_labels == normalized:
            return
        self._graphics_show_port_labels = normalized
        self.graphics_preferences_changed.emit()

    def set_payload_graphics_facts(
        self,
        *,
        show_port_labels: bool,
        graph_label_pixel_size: int,
        node_title_icon_pixel_size: int,
        lightweight_canvas: bool,
    ) -> None:
        self._graphics_show_port_labels = bool(show_port_labels)
        self._graphics_graph_label_pixel_size = int(graph_label_pixel_size)
        self._graphics_node_title_icon_pixel_size = int(
            node_title_icon_pixel_size
        )
        self._graphics_lightweight_canvas = bool(lightweight_canvas)
        self.graphics_preferences_changed.emit()

    @pyqtSlot(bool)
    def set_graphics_minimap_expanded(self, expanded: bool) -> None:
        normalized = bool(expanded)
        self.minimap_update_history.append(normalized)
        if self._graphics_minimap_expanded == normalized:
            return
        self._graphics_minimap_expanded = normalized
        self.graphics_preferences_changed.emit()


class GraphSceneBridgeTrackBTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QApplication.instance() or QApplication([])
        self.registry = build_default_registry()
        self.registry.register(_TrackBFlowchartDecisionNode)
        self.registry.register(_TrackBFlowchartConnectorNode)
        self.registry.register(_TrackBFlowchartPassthroughNode)
        self.registry.register(_TrackBSettingsGroupsNode)
        self.model = GraphModel()
        self.workspace_id = self.model.active_workspace.workspace_id
        self.preference_bridge = _GraphCanvasPreferenceBridge()
        self.scene = GraphSceneBridge()
        self.scene.bind_graphics_preferences_source(self.preference_bridge)
        self.scene.set_workspace(self.model, self.registry, self.workspace_id)
        self.view = ViewportBridge()
        self.view.set_viewport_size(1280.0, 720.0)

    def test_selection_signal_reports_select_and_clear(self) -> None:
        node_id = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        events: list[str] = []
        self.scene.node_selected.connect(events.append)

        self.scene.focus_node(node_id)
        self.assertEqual(events[-1], node_id)

        self.scene.clearSelection()
        self.assertEqual(events[-1], "")

    def test_node_addition_publishes_before_selection_notification(self) -> None:
        events: list[str] = []
        self.scene.nodes_changed.connect(lambda: events.append("nodes"))
        self.scene.selection_changed.connect(lambda: events.append("selection"))

        node_id = self.scene.add_node_from_type("core.constant", 40.0, 60.0)

        self.assertEqual(events, ["nodes", "selection"])
        self.assertEqual(self.scene.selected_node_id(), node_id)
        node_delta = self.scene.state_bridge.node_delta_payload
        self.assertEqual(node_delta["reason"], "node_addition_delta")
        self.assertEqual(node_delta["added_node_ids"], [node_id])

    def test_selection_only_updates_do_not_rebuild_models(self) -> None:
        node_a = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        node_b = self.scene.add_node_from_type("core.python_script", 320.0, 40.0)
        node_c = self.scene.add_node_from_type("core.logger", 640.0, 80.0)

        baseline_nodes = copy.deepcopy(self.scene.nodes_model)
        baseline_minimap = copy.deepcopy(self.scene.minimap_nodes_model)
        nodes_changed: list[str] = []
        edges_changed: list[str] = []
        selection_events: list[dict[str, bool]] = []
        node_selected_events: list[str] = []
        self.scene.nodes_changed.connect(lambda: nodes_changed.append("nodes"))
        self.scene.edges_changed.connect(lambda: edges_changed.append("edges"))
        self.scene.selection_changed.connect(
            lambda: selection_events.append(dict(self.scene.selected_node_lookup))
        )
        self.scene.node_selected.connect(node_selected_events.append)

        self.scene.select_node(node_b)
        self.assertEqual(self.scene.selected_node_id(), node_b)
        self.assertEqual(self.scene.selected_node_lookup, {node_b: True})
        self.assertEqual(selection_events[-1], {node_b: True})
        self.assertEqual(node_selected_events[-1], node_b)
        self.assertEqual(nodes_changed, [])
        self.assertEqual(edges_changed, [])
        self.assertEqual(self.scene.nodes_model, baseline_nodes)
        self.assertEqual(self.scene.minimap_nodes_model, baseline_minimap)

        selection_count_before = len(selection_events)
        node_selected_count_before = len(node_selected_events)
        self.scene.select_node(node_b)
        self.assertEqual(len(selection_events), selection_count_before)
        self.assertEqual(len(node_selected_events), node_selected_count_before)
        self.assertEqual(nodes_changed, [])
        self.assertEqual(edges_changed, [])

        self.scene.select_node(node_a, True)
        self.assertEqual(self.scene.selected_node_lookup, {node_b: True, node_a: True})
        self.assertEqual(selection_events[-1], {node_b: True, node_a: True})
        self.assertEqual(node_selected_events[-1], node_a)
        self.assertEqual(nodes_changed, [])
        self.assertEqual(edges_changed, [])
        self.assertEqual(self.scene.nodes_model, baseline_nodes)
        self.assertEqual(self.scene.minimap_nodes_model, baseline_minimap)

        self.scene.clearSelection()
        self.assertEqual(self.scene.selected_node_lookup, {})
        self.assertEqual(selection_events[-1], {})
        self.assertEqual(node_selected_events[-1], "")
        self.assertEqual(nodes_changed, [])
        self.assertEqual(edges_changed, [])
        self.assertEqual(self.scene.nodes_model, baseline_nodes)
        self.assertEqual(self.scene.minimap_nodes_model, baseline_minimap)

        focused_center = self.scene.focus_node(node_c)
        self.assertIsNotNone(focused_center)
        self.assertEqual(self.scene.selected_node_id(), node_c)
        self.assertEqual(self.scene.selected_node_lookup, {node_c: True})
        self.assertEqual(selection_events[-1], {node_c: True})
        self.assertEqual(node_selected_events[-1], node_c)
        self.assertEqual(nodes_changed, [])
        self.assertEqual(edges_changed, [])
        self.assertEqual(self.scene.nodes_model, baseline_nodes)
        self.assertEqual(self.scene.minimap_nodes_model, baseline_minimap)

    def test_connect_move_and_remove_keep_model_and_scene_in_sync(self) -> None:
        source_id = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        target_id = self.scene.add_node_from_type("core.python_script", 320.0, 40.0)
        edge_id = self.scene.connect_nodes(source_id, target_id)

        baseline_edges = {item["edge_id"]: copy.deepcopy(item) for item in self.scene.edges_model}
        nodes_changed: list[str] = []
        edges_changed: list[str] = []
        self.scene.nodes_changed.connect(lambda: nodes_changed.append("nodes"))
        self.scene.edges_changed.connect(lambda: edges_changed.append("edges"))
        rebuild_calls: list[str] = []
        original_rebuild_models = self.scene._scene_context.rebuild_models

        def _unexpected_rebuild_models() -> None:
            rebuild_calls.append("rebuild")
            original_rebuild_models()

        self.scene._scene_context.rebuild_models = _unexpected_rebuild_models
        try:
            self.scene.move_node(source_id, 120.0, 90.0)
        finally:
            self.scene._scene_context.rebuild_models = original_rebuild_models

        self.assertEqual(rebuild_calls, [])
        self.assertEqual(nodes_changed, ["nodes"])
        self.assertEqual(edges_changed, ["edges"])

        workspace = self.model.project.workspaces[self.workspace_id]
        source_model = workspace.nodes[source_id]
        self.assertAlmostEqual(source_model.x, 120.0, places=4)
        self.assertAlmostEqual(source_model.y, 90.0, places=4)
        source_payload = {item["node_id"]: item for item in self.scene.nodes_model}[source_id]
        moved_edge_payload = {item["edge_id"]: item for item in self.scene.edges_model}[edge_id]
        self.assertAlmostEqual(source_payload["x"], 120.0, places=4)
        self.assertAlmostEqual(source_payload["y"], 90.0, places=4)
        self.assertNotEqual(moved_edge_payload, baseline_edges[edge_id])
        edge_delta = self.scene.edge_delta_payload
        self.assertEqual(edge_delta["schema"], "graph_scene_edge_structural_delta")
        self.assertEqual(edge_delta["version"], 1)
        self.assertFalse(edge_delta["requires_full_refresh"])
        self.assertEqual(edge_delta["reason"], "node_position")
        self.assertEqual(edge_delta["added_edge_ids"], [])
        self.assertEqual(edge_delta["updated_edge_ids"], [edge_id])
        self.assertEqual(edge_delta["removed_edge_ids"], [])
        self.assertEqual(edge_delta["dirty_edge_ids"], [edge_id])
        self.assertEqual(edge_delta["dirty_node_ids"], [source_id])
        self.assertEqual(edge_delta["removed_node_ids"], [])
        self.assertCountEqual(edge_delta["affected_node_ids"], [source_id, target_id])
        self.assertEqual(edge_delta["edge_count_after"], 1)
        self.assertEqual(edge_delta["added_edges"], [])
        self.assertEqual(edge_delta["removed_edges"], [])
        self.assertEqual(len(edge_delta["updated_edges"]), 1)
        updated_entry = edge_delta["updated_edges"][0]
        self.assertEqual(updated_entry["edge_id"], edge_id)
        self.assertEqual(updated_entry["index"], 0)
        self.assertEqual(updated_entry["payload"]["edge_id"], edge_id)
        self.assertEqual(updated_entry["payload"]["source_node_id"], source_id)
        self.assertEqual(updated_entry["payload"]["target_node_id"], target_id)

        self.scene.remove_edge(edge_id)
        self.assertNotIn(edge_id, workspace.edges)
        self.assertIsNone(self.scene.edge_item(edge_id))

        new_edge_id = self.scene.add_edge(source_id, "value", target_id, "payload")
        self.scene.remove_node(source_id)
        self.assertNotIn(source_id, workspace.nodes)
        self.assertNotIn(new_edge_id, workspace.edges)
        self.assertIsNone(self.scene.node_item(source_id))
        self.assertIsNone(self.scene.edge_item(new_edge_id))

    def test_node_link_mutations_publish_targeted_node_payload(self) -> None:
        node_id = self.scene.add_node_from_type("core.logger", 20.0, 30.0)
        workspace = self.model.project.workspaces[self.workspace_id]

        nodes_changed: list[str] = []
        edges_changed: list[str] = []
        self.scene.nodes_changed.connect(lambda: nodes_changed.append("nodes"))
        self.scene.edges_changed.connect(lambda: edges_changed.append("edges"))
        rebuild_calls: list[str] = []
        original_rebuild_models = self.scene._scene_context.rebuild_models

        def _unexpected_rebuild_models() -> None:
            rebuild_calls.append("rebuild")
            original_rebuild_models()

        self.scene._scene_context.rebuild_models = _unexpected_rebuild_models
        try:
            self.assertEqual(
                self.scene.upsert_node_link(
                    node_id,
                    "link-docs",
                    "url",
                    "Project docs",
                    "https://example.com/docs",
                    "Reference",
                ),
                "link-docs",
            )
        finally:
            self.scene._scene_context.rebuild_models = original_rebuild_models

        self.assertEqual(rebuild_calls, [])
        self.assertEqual(nodes_changed, ["nodes"])
        self.assertEqual(edges_changed, [])
        payload = next(item for item in self.scene.nodes_model if item["node_id"] == node_id)
        self.assertEqual(payload["link_count"], 1)
        self.assertEqual(
            payload["links"],
            [
                {
                    "id": "link-docs",
                    "kind": "url",
                    "title": "Project docs",
                    "target": "https://example.com/docs",
                    "subtitle": "Reference",
                }
            ],
        )
        node_delta = getattr(self.scene.state_bridge, "node_delta_payload", {})
        self.assertEqual(node_delta["kind"], "node_delta")
        self.assertEqual(node_delta["reason"], "node_link_payload")
        self.assertEqual([payload["node_id"] for payload in node_delta["nodes"]], [node_id])
        self.assertFalse(node_delta["visibility_may_change"])
        self.assertEqual(self.scene.edge_delta_payload, {})

        self.assertEqual(
            self.scene.upsert_node_link(node_id, "link-node", "node", "Start", "node-start", ""),
            "link-node",
        )
        self.assertTrue(self.scene.move_node_link(node_id, "link-node", -1))
        payload = next(item for item in self.scene.nodes_model if item["node_id"] == node_id)
        self.assertEqual([item["id"] for item in payload["links"]], ["link-node", "link-docs"])
        self.assertEqual(payload["link_count"], 2)

        self.scene.set_node_property(node_id, "message", "[Project docs](corex-link:link-docs)")
        self.assertTrue(self.scene.remove_node_link(node_id, "link-docs"))
        payload = next(item for item in self.scene.nodes_model if item["node_id"] == node_id)
        self.assertEqual([item["id"] for item in payload["links"]], ["link-node"])
        self.assertEqual(payload["link_count"], 1)
        self.assertEqual(workspace.nodes[node_id].properties["message"], "Project docs")

    def test_targeted_payload_routes_forward_all_graphics_facts(self) -> None:
        source_id = self.scene.add_node_from_type("core.constant", 20.0, 30.0)
        target_id = self.scene.add_node_from_type("core.python_script", 320.0, 30.0)
        self.preference_bridge.set_payload_graphics_facts(
            show_port_labels=False,
            graph_label_pixel_size=16,
            node_title_icon_pixel_size=12,
            lightweight_canvas=True,
        )
        expected = {
            "show_port_labels": False,
            "graph_label_pixel_size": 16,
            "graph_node_icon_pixel_size": 12,
            "lightweight_canvas": True,
        }
        builder = self.scene._payload_builder

        with patch.object(
            builder,
            "build_node_payloads_for_ids",
            wraps=builder.build_node_payloads_for_ids,
        ) as build_node_payloads:
            self.assertEqual(
                self.scene.upsert_node_link(
                    source_id,
                    "link-docs",
                    "url",
                    "Project docs",
                    "https://example.com/docs",
                    "Reference",
                ),
                "link-docs",
            )
        with patch.object(
            builder,
            "build_node_connection_payloads_for_ids",
            wraps=builder.build_node_connection_payloads_for_ids,
        ) as build_connection_payloads:
            self.scene.add_edge(source_id, "value", target_id, "payload")

        for route, call in (
            ("full_node", build_node_payloads.call_args),
            ("connection", build_connection_payloads.call_args),
        ):
            with self.subTest(route=route):
                self.assertIsNotNone(call)
                self.assertEqual(
                    {name: call.kwargs[name] for name in expected},
                    expected,
                )

    def test_node_comment_mutations_publish_targeted_node_payload_and_persist(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        node_id = self.scene.add_node_from_type("core.logger", 20.0, 30.0)
        workspace = self.model.project.workspaces[self.workspace_id]
        history.clear_workspace(self.workspace_id)

        nodes_changed: list[str] = []
        edges_changed: list[str] = []
        self.scene.nodes_changed.connect(lambda: nodes_changed.append("nodes"))
        self.scene.edges_changed.connect(lambda: edges_changed.append("edges"))
        rebuild_calls: list[str] = []
        original_rebuild_models = self.scene._scene_context.rebuild_models

        def _unexpected_rebuild_models() -> None:
            rebuild_calls.append("rebuild")
            original_rebuild_models()

        self.scene._scene_context.rebuild_models = _unexpected_rebuild_models
        try:
            self.assertEqual(
                self.scene.upsert_node_comment(
                    node_id,
                    "comment-open",
                    "Check the resample step.",
                    "Analyst",
                    "",
                    False,
                    True,
                    False,
                ),
                "comment-open",
            )
        finally:
            self.scene._scene_context.rebuild_models = original_rebuild_models

        self.assertEqual(rebuild_calls, [])
        self.assertEqual(nodes_changed, ["nodes"])
        self.assertEqual(edges_changed, [])
        payload = next(item for item in self.scene.nodes_model if item["node_id"] == node_id)
        self.assertEqual(payload["comment_count"], 1)
        self.assertEqual(payload["comments"][0]["id"], "comment-open")
        self.assertEqual(payload["comments"][0]["author"], "Analyst")
        self.assertEqual(payload["comment_badge"]["count"], 1)
        self.assertEqual(payload["comment_badge"]["open_count"], 1)
        self.assertFalse(payload["comment_badge"]["resolved_all"])
        self.assertTrue(payload["comment_badge"]["unread"])
        self.assertEqual(payload["comment_badge"]["preview_comments"][0]["body"], "Check the resample step.")
        node_delta = getattr(self.scene.state_bridge, "node_delta_payload", {})
        self.assertEqual(node_delta["kind"], "node_delta")
        self.assertEqual(node_delta["reason"], "node_comment_payload")
        self.assertEqual([payload["node_id"] for payload in node_delta["nodes"]], [node_id])
        self.assertFalse(node_delta["visibility_may_change"])
        self.assertEqual(self.scene.edge_delta_payload, {})

        self.assertEqual(
            self.scene.upsert_node_comment(
                node_id,
                "comment-reply",
                "Added a guard.",
                "Reviewer",
                "comment-open",
                False,
                True,
                False,
            ),
            "comment-reply",
        )
        self.assertEqual(
            self.scene.upsert_node_comment(
                node_id,
                "comment-grandchild",
                "Nested follow-up.",
                "Reviewer",
                "comment-reply",
                False,
                True,
                False,
            ),
            "comment-grandchild",
        )
        self.assertTrue(self.scene.set_node_comment_pinned(node_id, "comment-reply", True))
        payload = next(item for item in self.scene.nodes_model if item["node_id"] == node_id)
        self.assertEqual(payload["comment_count"], 3)
        self.assertEqual(payload["comment_badge"]["preview_comments"][0]["id"], "comment-reply")
        self.assertEqual(payload["comment_badge"]["preview_comments"][1]["id"], "comment-open")

        self.assertEqual(
            self.scene.upsert_node_comment(
                node_id,
                "comment-open",
                "Check the resample step before export.",
                "",
                "",
                False,
                True,
                True,
            ),
            "comment-open",
        )
        self.assertEqual(workspace.nodes[node_id].comments[0].body, "Check the resample step before export.")
        history.clear_workspace(self.workspace_id)
        self.assertTrue(self.scene.mark_node_comments_read(node_id))
        self.assertEqual(history.undo_depth(self.workspace_id), 1)
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_EDIT_NODE_COMMENT)
        self.assertFalse(any(comment.unread for comment in workspace.nodes[node_id].comments))
        self.assertIsNotNone(history.undo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertTrue(any(comment.unread for comment in workspace.nodes[node_id].comments))
        self.assertIsNotNone(history.redo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertFalse(any(comment.unread for comment in workspace.nodes[node_id].comments))
        self.assertTrue(self.scene.resolve_all_node_comments(node_id))
        payload = next(item for item in self.scene.nodes_model if item["node_id"] == node_id)
        self.assertEqual(payload["comment_badge"]["open_count"], 0)
        self.assertTrue(payload["comment_badge"]["resolved_all"])

        mapping = node_instance_to_mapping(workspace.nodes[node_id])
        mapping["comments"][0]["resolved"] = "false"
        mapping["comments"][0]["unread"] = "false"
        mapping["comments"][0]["pinned"] = "false"
        restored = node_instance_from_mapping(mapping)
        self.assertEqual(
            [comment.comment_id for comment in restored.comments],
            ["comment-open", "comment-reply", "comment-grandchild"],
        )
        self.assertFalse(restored.comments[0].resolved)
        self.assertFalse(restored.comments[0].unread)
        self.assertFalse(restored.comments[0].pinned)
        self.assertEqual(restored.comments[1].parent_id, "comment-open")
        self.assertEqual(restored.comments[2].parent_id, "comment-reply")

        self.assertTrue(self.scene.remove_node_comment(node_id, "comment-open"))
        payload = next(item for item in self.scene.nodes_model if item["node_id"] == node_id)
        self.assertEqual(payload["comment_count"], 0)
        self.assertEqual(payload["comment_badge"]["count"], 0)
        self.assertEqual(workspace.nodes[node_id].comments, [])

    def test_resize_node_geometry_uses_targeted_delta_without_scene_rebuild(self) -> None:
        source_id = self.scene.add_node_from_type("io.path_pointer", 0.0, 0.0)
        target_id = self.scene.add_node_from_type("core.python_script", 320.0, 40.0)
        edge_id = self.scene.connect_nodes(source_id, target_id)
        workspace = self.model.project.workspaces[self.workspace_id]
        source_node = workspace.nodes[source_id]
        baseline_edges = {item["edge_id"]: copy.deepcopy(item) for item in self.scene.edges_model}
        source_payload_before = {item["node_id"]: item for item in self.scene.nodes_model}[source_id]
        next_width = float(source_payload_before["width"]) + 44.0
        next_height = float(source_payload_before["height"]) + 18.0

        nodes_changed: list[str] = []
        edges_changed: list[str] = []
        self.scene.nodes_changed.connect(lambda: nodes_changed.append("nodes"))
        self.scene.edges_changed.connect(lambda: edges_changed.append("edges"))
        rebuild_calls: list[str] = []
        original_rebuild_models = self.scene._scene_context.rebuild_models

        def _unexpected_rebuild_models() -> None:
            rebuild_calls.append("rebuild")
            original_rebuild_models()

        self.scene._scene_context.rebuild_models = _unexpected_rebuild_models
        try:
            self.scene.set_node_geometry(
                source_id,
                float(source_node.x),
                float(source_node.y),
                next_width,
                next_height,
            )
        finally:
            self.scene._scene_context.rebuild_models = original_rebuild_models

        self.assertEqual(rebuild_calls, [])
        self.assertEqual(nodes_changed, ["nodes"])
        self.assertEqual(edges_changed, ["edges"])
        self.assertAlmostEqual(workspace.nodes[source_id].custom_width or 0.0, next_width, places=6)
        self.assertAlmostEqual(workspace.nodes[source_id].custom_height or 0.0, next_height, places=6)

        node_payload = {item["node_id"]: item for item in self.scene.nodes_model}[source_id]
        edge_payload = {item["edge_id"]: item for item in self.scene.edges_model}[edge_id]
        self.assertAlmostEqual(node_payload["width"], next_width, places=6)
        self.assertAlmostEqual(node_payload["height"], next_height, places=6)
        self.assertNotEqual(edge_payload, baseline_edges[edge_id])

        edge_delta = self.scene.edge_delta_payload
        self.assertEqual(edge_delta["schema"], "graph_scene_edge_structural_delta")
        self.assertEqual(edge_delta["version"], 1)
        self.assertFalse(edge_delta["requires_full_refresh"])
        self.assertEqual(edge_delta["reason"], "node_geometry")
        self.assertEqual(edge_delta["added_edge_ids"], [])
        self.assertEqual(edge_delta["updated_edge_ids"], [edge_id])
        self.assertEqual(edge_delta["removed_edge_ids"], [])
        self.assertEqual(edge_delta["dirty_edge_ids"], [edge_id])
        self.assertEqual(edge_delta["dirty_node_ids"], [source_id])
        self.assertEqual(edge_delta["removed_node_ids"], [])
        self.assertCountEqual(edge_delta["affected_node_ids"], [source_id, target_id])
        self.assertEqual(edge_delta["edge_count_after"], 1)

    def test_resize_node_clamps_to_surface_minimum_and_records_history(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        node_id = self.scene.add_node_from_type("io.path_pointer", 20.0, 30.0)
        workspace = self.model.project.workspaces[self.workspace_id]
        history.clear_workspace(self.workspace_id)

        self.scene.resize_node(node_id, 10.0, 5.0)

        node = workspace.nodes[node_id]
        payload = next(item for item in self.scene.nodes_model if item["node_id"] == node_id)
        self.assertEqual(history.undo_depth(self.workspace_id), 1)
        self.assertGreaterEqual(float(node.custom_width or 0.0), 120.0)
        self.assertAlmostEqual(float(node.custom_height or 0.0), float(payload["surface_metrics"]["min_height"]), places=6)
        self.assertAlmostEqual(payload["width"], float(node.custom_width or 0.0), places=6)
        self.assertAlmostEqual(payload["height"], float(node.custom_height or 0.0), places=6)

        self.assertIsNotNone(history.undo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertIsNone(workspace.nodes[node_id].custom_width)
        self.assertIsNone(workspace.nodes[node_id].custom_height)

    def test_same_type_selection_resizes_only_passive_buckets_with_grouped_history(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        process_primary = self.scene.add_node_from_type("passive.flowchart.process", 40.0, 60.0)
        note_primary = self.scene.add_node_from_type("passive.annotation.sticky_note", 300.0, 80.0)
        active_primary = self.scene.add_node_from_type("core.logger", 560.0, 100.0)
        compile_primary = self.scene.add_node_from_type("core.subnode", 820.0, 120.0)
        process_target = self.scene.add_node_from_type("passive.flowchart.process", 40.0, 360.0)
        note_target = self.scene.add_node_from_type("passive.annotation.sticky_note", 300.0, 380.0)
        active_target = self.scene.add_node_from_type("core.logger", 560.0, 400.0)
        compile_target = self.scene.add_node_from_type("core.subnode", 820.0, 420.0)
        workspace = self.model.project.workspaces[self.workspace_id]

        widths = {
            process_primary: 320.0,
            note_primary: 360.0,
            active_primary: 400.0,
            compile_primary: 420.0,
            process_target: 220.0,
            note_target: 240.0,
            active_target: 260.0,
            compile_target: 280.0,
        }
        for node_id, width in widths.items():
            workspace.nodes[node_id].custom_width = width
        self.scene.refresh_workspace_from_model(self.workspace_id)
        history.clear_workspace(self.workspace_id)

        changed = self.scene.set_selected_same_type_size(
            [
                process_primary,
                note_primary,
                active_primary,
                compile_primary,
                process_target,
                note_target,
                active_target,
                compile_target,
            ],
            "width",
        )

        self.assertTrue(changed)
        self.assertEqual(history.undo_depth(self.workspace_id), 1)
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_RESIZE_NODE)
        self.assertAlmostEqual(workspace.nodes[process_target].custom_width or 0.0, 320.0, places=6)
        self.assertAlmostEqual(workspace.nodes[note_target].custom_width or 0.0, 360.0, places=6)
        self.assertAlmostEqual(workspace.nodes[active_target].custom_width or 0.0, 260.0, places=6)
        self.assertAlmostEqual(workspace.nodes[compile_target].custom_width or 0.0, 280.0, places=6)
        self.assertFalse(
            self.scene.set_selected_same_type_size(
                [process_primary, note_primary, process_target, note_target],
                "width",
            )
        )
        self.assertEqual(history.undo_depth(self.workspace_id), 1)

        self.assertIsNotNone(history.undo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        for node_id, width in widths.items():
            self.assertAlmostEqual(workspace.nodes[node_id].custom_width or 0.0, width, places=6)

    def test_same_type_selection_rejects_active_and_compile_only_buckets(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        active_primary = self.scene.add_node_from_type("core.logger", 40.0, 60.0)
        active_target = self.scene.add_node_from_type("core.logger", 340.0, 90.0)
        compile_primary = self.scene.add_node_from_type("core.subnode", 640.0, 120.0)
        compile_target = self.scene.add_node_from_type("core.subnode", 940.0, 160.0)
        workspace = self.model.project.workspaces[self.workspace_id]
        workspace.nodes[active_primary].custom_width = 320.0
        workspace.nodes[active_target].custom_width = 220.0
        workspace.nodes[compile_primary].custom_height = 240.0
        workspace.nodes[compile_target].custom_height = 160.0
        self.scene.refresh_workspace_from_model(self.workspace_id)
        history.clear_workspace(self.workspace_id)

        self.assertFalse(self.scene.set_selected_same_type_size([active_primary, active_target], "width"))
        self.assertFalse(self.scene.set_selected_same_type_size([compile_primary, compile_target], "height"))
        self.assertFalse(self.scene.set_selected_same_type_size([active_primary, active_target], "depth"))
        self.assertAlmostEqual(workspace.nodes[active_target].custom_width or 0.0, 220.0, places=6)
        self.assertAlmostEqual(workspace.nodes[compile_target].custom_height or 0.0, 160.0, places=6)
        self.assertEqual(history.undo_depth(self.workspace_id), 0)

    def test_collapse_expand_updates_node_payload(self) -> None:
        source_id = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        self.scene.set_node_collapsed(source_id, True)

        payload = {item["node_id"]: item for item in self.scene.nodes_model}
        self.assertTrue(payload[source_id]["collapsed"])
        self.assertLess(payload[source_id]["width"], 150.0)

        self.scene.set_node_collapsed(source_id, False)
        payload = {item["node_id"]: item for item in self.scene.nodes_model}
        self.assertFalse(payload[source_id]["collapsed"])

    def test_settings_group_toggle_preserves_custom_body_and_groups_history(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        node_id = self.scene.add_node_from_type(
            "tests.track_b_settings_groups",
            40.0,
            60.0,
        )
        neighbor_id = self.scene.add_node_from_type("core.constant", 300.0, 80.0)
        workspace = self.model.project.workspaces[self.workspace_id]
        before_payload = next(
            item for item in self.scene.nodes_model if item["node_id"] == node_id
        )
        before_height = float(before_payload["height"])
        before_band_height = float(before_payload["settings_band"]["height"])
        workspace.nodes[node_id].custom_height = before_height
        self.scene.refresh_workspace_from_model(self.workspace_id)
        history.clear_workspace(self.workspace_id)
        neighbor_before = (
            float(workspace.nodes[neighbor_id].x),
            float(workspace.nodes[neighbor_id].y),
        )
        neighbor_after = (neighbor_before[0] + 90.0, neighbor_before[1] + 30.0)

        with patch(
            "ea_node_editor.ui_qml.graph_scene_mutation.selection_and_scope_ops."
            "expand_collision_avoidance_updates",
            return_value={neighbor_id: neighbor_after},
        ):
            self.assertTrue(
                self.scene.command_bridge.set_node_settings_group_expanded(
                    node_id,
                    "general",
                    True,
                )
            )

        node = workspace.nodes[node_id]
        after_payload = next(
            item for item in self.scene.nodes_model if item["node_id"] == node_id
        )
        after_band_height = float(after_payload["settings_band"]["height"])
        self.assertEqual(node.expanded_settings_group_ids, ("general",))
        self.assertAlmostEqual(
            float(node.custom_height or 0.0),
            before_height + after_band_height - before_band_height,
            places=6,
        )
        self.assertAlmostEqual(
            float(after_payload["height"]) - after_band_height,
            before_height - before_band_height,
            places=6,
        )
        self.assertEqual(
            (workspace.nodes[neighbor_id].x, workspace.nodes[neighbor_id].y),
            neighbor_after,
        )
        self.assertEqual(history.undo_depth(self.workspace_id), 1)
        self.assertEqual(
            history._undo_stacks[self.workspace_id][-1].action_type,
            ACTION_TOGGLE_SETTINGS_GROUP,
        )

        self.assertIsNotNone(history.undo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertEqual(workspace.nodes[node_id].expanded_settings_group_ids, ())
        self.assertAlmostEqual(
            float(workspace.nodes[node_id].custom_height or 0.0),
            before_height,
            places=6,
        )
        self.assertEqual(
            (workspace.nodes[neighbor_id].x, workspace.nodes[neighbor_id].y),
            neighbor_before,
        )

        self.assertIsNotNone(history.redo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertEqual(
            workspace.nodes[node_id].expanded_settings_group_ids,
            ("general",),
        )
        self.assertEqual(
            (workspace.nodes[neighbor_id].x, workspace.nodes[neighbor_id].y),
            neighbor_after,
        )

        self.assertTrue(
            self.scene.command_bridge.set_node_settings_group_expanded(
                node_id,
                "general",
                False,
            )
        )
        collapsed_payload = next(
            item for item in self.scene.nodes_model if item["node_id"] == node_id
        )
        self.assertEqual(workspace.nodes[node_id].expanded_settings_group_ids, ())
        self.assertAlmostEqual(
            float(workspace.nodes[node_id].custom_height or 0.0),
            before_height,
            places=6,
        )
        self.assertAlmostEqual(
            float(collapsed_payload["height"])
            - float(collapsed_payload["settings_band"]["height"]),
            before_height - before_band_height,
            places=6,
        )

    def test_settings_group_expansion_moves_a_real_overlapping_neighbor(self) -> None:
        node_id = self.scene.add_node_from_type(
            "tests.track_b_settings_groups",
            40.0,
            60.0,
        )
        before_payload = next(
            item for item in self.scene.nodes_model if item["node_id"] == node_id
        )
        neighbor_id = self.scene.add_node_from_type(
            "core.constant",
            50.0,
            60.0 + float(before_payload["height"]) + 40.0,
        )
        workspace = self.model.project.workspaces[self.workspace_id]
        workspace.nodes[node_id].custom_height = float(before_payload["height"])
        self.scene.refresh_workspace_from_model(self.workspace_id)
        neighbor_before = (
            float(workspace.nodes[neighbor_id].x),
            float(workspace.nodes[neighbor_id].y),
        )

        self.assertTrue(
            self.scene.command_bridge.set_node_settings_group_expanded(
                node_id,
                "general",
                True,
            )
        )

        self.assertNotEqual(
            (workspace.nodes[neighbor_id].x, workspace.nodes[neighbor_id].y),
            neighbor_before,
        )

    def test_settings_group_toggle_validates_group_and_locked_node(self) -> None:
        node_id = self.scene.add_node_from_type(
            "tests.track_b_settings_groups",
            40.0,
            60.0,
        )
        workspace = self.model.project.workspaces[self.workspace_id]
        node = workspace.nodes[node_id]

        self.assertFalse(
            self.scene.set_node_settings_group_expanded(node_id, "missing", True)
        )
        self.assertEqual(node.expanded_settings_group_ids, ())

        node.locked = True
        self.assertFalse(
            self.scene.set_node_settings_group_expanded(node_id, "general", True)
        )
        self.assertEqual(node.expanded_settings_group_ids, ())

    def test_settings_group_toggle_while_node_collapsed_preserves_reopened_body(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        node_id = self.scene.add_node_from_type(
            "tests.track_b_settings_groups",
            40.0,
            60.0,
        )
        workspace = self.model.project.workspaces[self.workspace_id]
        baseline_payload = next(
            item for item in self.scene.nodes_model if item["node_id"] == node_id
        )
        baseline_height = float(baseline_payload["height"])
        baseline_band_height = float(baseline_payload["settings_band"]["height"])
        baseline_body_height = baseline_height - baseline_band_height
        workspace.nodes[node_id].custom_height = baseline_height
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.scene.set_node_collapsed(node_id, True)
        history.clear_workspace(self.workspace_id)

        self.assertTrue(
            self.scene.set_node_settings_group_expanded(node_id, "general", True)
        )
        expanded_group_height = float(workspace.nodes[node_id].custom_height or 0.0)
        self.assertTrue(workspace.nodes[node_id].collapsed)
        self.assertEqual(
            workspace.nodes[node_id].expanded_settings_group_ids,
            ("general",),
        )
        self.assertGreater(expanded_group_height, baseline_height)
        self.assertEqual(history.undo_depth(self.workspace_id), 1)

        self.scene.set_node_collapsed(node_id, False)
        reopened_payload = next(
            item for item in self.scene.nodes_model if item["node_id"] == node_id
        )
        self.assertAlmostEqual(
            float(reopened_payload["height"])
            - float(reopened_payload["settings_band"]["height"]),
            baseline_body_height,
            places=6,
        )

        self.assertIsNotNone(history.undo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertTrue(workspace.nodes[node_id].collapsed)
        self.assertEqual(
            workspace.nodes[node_id].expanded_settings_group_ids,
            ("general",),
        )
        self.assertIsNotNone(history.undo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertTrue(workspace.nodes[node_id].collapsed)
        self.assertEqual(workspace.nodes[node_id].expanded_settings_group_ids, ())
        self.assertAlmostEqual(
            float(workspace.nodes[node_id].custom_height or 0.0),
            baseline_height,
            places=6,
        )

        self.assertIsNotNone(history.redo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertTrue(workspace.nodes[node_id].collapsed)
        self.assertEqual(
            workspace.nodes[node_id].expanded_settings_group_ids,
            ("general",),
        )
        self.assertAlmostEqual(
            float(workspace.nodes[node_id].custom_height or 0.0),
            expanded_group_height,
            places=6,
        )
        self.assertIsNotNone(history.redo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        final_payload = next(
            item for item in self.scene.nodes_model if item["node_id"] == node_id
        )
        self.assertFalse(workspace.nodes[node_id].collapsed)
        self.assertAlmostEqual(
            float(final_payload["height"])
            - float(final_payload["settings_band"]["height"]),
            baseline_body_height,
            places=6,
        )

    def test_passive_node_lock_persists_and_interaction_mode_controls_selection(self) -> None:
        node_id = self.scene.add_node_from_type("passive.annotation.text", 40.0, 60.0)
        active_id = self.scene.add_node_from_type("core.constant", 400.0, 60.0)
        workspace = self.model.project.workspaces[self.workspace_id]

        self.scene.select_node(node_id, False)
        self.assertTrue(self.scene.command_bridge.set_node_locked(node_id, True))
        self.assertTrue(workspace.nodes[node_id].locked)
        self.assertEqual(self.scene.selected_node_ids, [])
        self.assertTrue(next(item for item in self.scene.nodes_model if item["node_id"] == node_id)["locked"])

        mapping = node_instance_to_mapping(workspace.nodes[node_id])
        self.assertTrue(mapping["locked"])
        self.assertTrue(node_instance_from_mapping(mapping).locked)

        self.scene.select_node(node_id, False)
        self.assertEqual(self.scene.selected_node_ids, [])
        self.scene.select_nodes_in_rect(0.0, 0.0, 300.0, 240.0, False)
        self.assertEqual(self.scene.selected_node_ids, [])

        self.assertTrue(self.scene.set_interact_with_locked_objects(True))
        self.assertTrue(self.scene.state_bridge.interact_with_locked_objects)
        self.scene.select_node(node_id, False)
        self.assertEqual(self.scene.selected_node_ids, [node_id])
        fragment = self.scene.serialize_selected_subgraph_fragment()
        self.assertIsNotNone(fragment)
        self.assertTrue(fragment["nodes"][0]["locked"])
        before_paste_ids = set(workspace.nodes)
        self.assertTrue(self.scene.paste_subgraph_fragment(fragment, 760.0, 180.0))
        pasted_ids = set(workspace.nodes).difference(before_paste_ids)
        self.assertEqual(len(pasted_ids), 1)
        self.assertTrue(workspace.nodes[pasted_ids.pop()].locked)
        self.assertTrue(self.scene.set_interact_with_locked_objects(False))
        self.assertEqual(self.scene.selected_node_ids, [])

        self.assertFalse(self.scene.command_bridge.set_node_locked(active_id, True))
        self.assertFalse(workspace.nodes[active_id].locked)
        self.scene.set_interact_with_locked_objects(True)
        self.scene.select_node(node_id, False)
        self.assertTrue(self.scene.command_bridge.set_node_locked(node_id, False))
        self.assertEqual(self.scene.selected_node_ids, [node_id])
        self.assertFalse(workspace.nodes[node_id].locked)

    def test_scene_payloads_include_node_and_edge_visual_metadata_contracts(self) -> None:
        source_id = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        target_id = self.scene.add_node_from_type("core.python_script", 320.0, 40.0)
        passive_id = self.scene.add_node_from_type("passive.flowchart.process", 640.0, 80.0)
        edge_id = self.scene.add_edge(source_id, "value", target_id, "payload")
        workspace = self.model.project.workspaces[self.workspace_id]
        workspace.nodes[source_id].visual_style = {"fill": "#102030", "badge": {"shape": "pill"}}
        workspace.nodes[passive_id].visual_style = {"fill": "#405060"}
        workspace.edges[edge_id].label = "Primary path"
        workspace.edges[edge_id].visual_style = {"stroke": "dashed", "arrow": {"kind": "none"}}

        self.scene.refresh_workspace_from_model(self.workspace_id)

        node_payload = {item["node_id"]: item for item in self.scene.nodes_model}
        edge_payload = {item["edge_id"]: item for item in self.scene.edges_model}

        self.assertEqual(node_payload[source_id]["runtime_behavior"], "active")
        self.assertEqual(node_payload[source_id]["surface_family"], "standard")
        self.assertEqual(node_payload[source_id]["surface_variant"], "")
        surface_metrics = node_payload[source_id]["surface_metrics"]
        self.assertEqual(surface_metrics["default_width"], 210.0)
        self.assertAlmostEqual(
            surface_metrics["min_width"],
            max(
                surface_metrics["standard_title_full_width"],
                surface_metrics["standard_port_label_min_width"],
            ),
            places=6,
        )
        self.assertEqual(surface_metrics["min_height"], surface_metrics["default_height"])
        self.assertEqual(surface_metrics["standard_left_label_width"], 0.0)
        self.assertGreater(surface_metrics["standard_right_label_width"], 0.0)
        self.assertEqual(surface_metrics["standard_port_gutter"], 11.5)
        self.assertEqual(surface_metrics["standard_center_gap"], 24.0)
        self.assertNotIn("visual_style", node_payload[source_id])
        self.assertEqual(node_payload[passive_id]["visual_style"], {"fill": "#405060"})
        self.assertEqual(edge_payload[edge_id]["label"], "Primary path")
        self.assertEqual(
            edge_payload[edge_id]["visual_style"],
            {
                "stroke": "dashed",
                "arrow": {"kind": "none"},
                "display_mode": "default",
            },
        )
        self.assertEqual(edge_payload[edge_id]["source_port_kind"], "data")
        self.assertEqual(edge_payload[edge_id]["target_port_kind"], "data")

    def test_standard_node_min_width_tracks_port_label_visibility_preference(self) -> None:
        node_id = self.scene.add_node_from_type("core.if", 40.0, 60.0)
        self.scene.set_node_port_label(node_id, "condition", "Primary Input Payload")
        self.scene.set_node_port_label(node_id, "result", "Dispatch Result Token")

        self.preference_bridge.set_graphics_show_port_labels_value(False)
        self.scene.refresh_workspace_from_model(self.workspace_id)
        payload_by_id = {item["node_id"]: item for item in self.scene.nodes_model}
        off_metrics = payload_by_id[node_id]["surface_metrics"]

        self.preference_bridge.set_graphics_show_port_labels_value(True)
        self.scene.refresh_workspace_from_model(self.workspace_id)
        payload_by_id = {item["node_id"]: item for item in self.scene.nodes_model}
        on_metrics = payload_by_id[node_id]["surface_metrics"]

        self.assertGreaterEqual(off_metrics["min_width"], off_metrics["standard_title_full_width"])
        self.assertGreater(on_metrics["min_width"], off_metrics["min_width"])
        self.assertGreater(on_metrics["standard_left_label_width"], 0.0)
        self.assertGreater(on_metrics["standard_right_label_width"], 0.0)
        self.assertGreater(on_metrics["standard_port_label_min_width"], on_metrics["standard_title_full_width"])
        self.assertAlmostEqual(
            on_metrics["min_width"],
            max(
                off_metrics["min_width"],
                on_metrics["standard_title_full_width"],
                on_metrics["standard_port_label_min_width"],
            ),
            places=6,
        )

    def test_minimap_expansion_preference_does_not_rebuild_scene_payload(self) -> None:
        self.scene.add_node_from_type("core.logger", 40.0, 60.0)
        self.assertGreater(len(self.scene.nodes_model), 0)

        rebuild_calls: list[str] = []
        original_rebuild_models = self.scene._scene_context.rebuild_models

        def _unexpected_rebuild_models() -> None:
            rebuild_calls.append("rebuild")
            original_rebuild_models()

        self.scene._scene_context.rebuild_models = _unexpected_rebuild_models
        try:
            self.preference_bridge.set_graphics_minimap_expanded(False)
        finally:
            self.scene._scene_context.rebuild_models = original_rebuild_models

        self.assertFalse(self.preference_bridge.graphics_minimap_expanded)
        self.assertEqual(rebuild_calls, [])

    def test_payload_affecting_graphics_preference_rebuilds_scene_payload(self) -> None:
        self.scene.add_node_from_type("core.logger", 40.0, 60.0)
        self.assertGreater(len(self.scene.nodes_model), 0)

        rebuild_calls: list[str] = []
        original_rebuild_models = self.scene._scene_context.rebuild_models

        def _record_rebuild_models() -> None:
            rebuild_calls.append("rebuild")
            original_rebuild_models()

        self.scene._scene_context.rebuild_models = _record_rebuild_models
        try:
            self.preference_bridge.set_graphics_show_port_labels_value(False)
        finally:
            self.scene._scene_context.rebuild_models = original_rebuild_models

        self.assertFalse(self.preference_bridge.graphics_show_port_labels)
        self.assertEqual(rebuild_calls, ["rebuild"])

    def test_standard_node_min_width_contract_matches_qt_label_widths(self) -> None:
        node_id = self.scene.add_node_from_type("core.if", 40.0, 60.0)
        self.scene.set_node_port_label(node_id, "condition", "payload")
        self.scene.set_node_port_label(node_id, "result", "result")

        self.preference_bridge.set_graphics_show_port_labels_value(True)
        self.scene.refresh_workspace_from_model(self.workspace_id)
        payload_by_id = {item["node_id"]: item for item in self.scene.nodes_model}
        metrics = payload_by_id[node_id]["surface_metrics"]

        font = QFont(self.app.font())
        font.setPixelSize(10)
        font_metrics = QFontMetricsF(font)
        expected_left_width = float(font_metrics.horizontalAdvance("payload") + 2.0)
        expected_right_width = float(font_metrics.horizontalAdvance("result") + 2.0)
        expected_port_label_min_width = (
            expected_left_width
            + expected_right_width
            + (float(metrics["standard_port_gutter"]) * 2.0)
            + float(metrics["standard_center_gap"])
        )

        self.assertGreaterEqual(float(metrics["standard_left_label_width"]), expected_left_width - 0.5)
        self.assertGreaterEqual(float(metrics["standard_right_label_width"]), expected_right_width - 0.5)
        self.assertGreaterEqual(float(metrics["standard_port_label_min_width"]), expected_port_label_min_width - 1.0)
        self.assertGreaterEqual(float(metrics["min_width"]), expected_port_label_min_width - 1.0)

    def test_standard_node_rendered_width_and_resize_clamp_share_preference_aware_min_width(self) -> None:
        node_id = self.scene.add_node_from_type("core.if", 40.0, 60.0)
        # Labels long enough that the labels-on min width exceeds the custom
        # width set below even with the edge-anchored grip gutter (11.5).
        self.scene.set_node_port_label(node_id, "condition", "Primary Input Payload Stream Reference")
        self.scene.set_node_port_label(node_id, "result", "Dispatch Result Token Stream Reference")
        workspace = self.model.project.workspaces[self.workspace_id]
        node = workspace.nodes[node_id]

        self.preference_bridge.set_graphics_show_port_labels_value(False)
        self.scene.refresh_workspace_from_model(self.workspace_id)
        payload_by_id = {item["node_id"]: item for item in self.scene.nodes_model}
        off_payload = payload_by_id[node_id]
        off_width = float(off_payload["surface_metrics"]["min_width"]) + 18.0

        self.scene.set_node_geometry(
            node_id,
            float(node.x),
            float(node.y),
            off_width,
            float(off_payload["height"]),
        )
        payload_by_id = {item["node_id"]: item for item in self.scene.nodes_model}
        off_payload = payload_by_id[node_id]
        self.assertAlmostEqual(off_payload["width"], off_payload["surface_metrics"]["default_width"], places=6)
        self.assertAlmostEqual(float(workspace.nodes[node_id].custom_width or 0.0), off_width, places=6)

        self.preference_bridge.set_graphics_show_port_labels_value(True)
        self.scene.refresh_workspace_from_model(self.workspace_id)
        payload_by_id = {item["node_id"]: item for item in self.scene.nodes_model}
        on_payload = payload_by_id[node_id]
        on_min_width = float(on_payload["surface_metrics"]["min_width"])

        self.assertGreater(on_min_width, off_width)
        self.assertAlmostEqual(on_payload["width"], on_min_width, places=6)
        self.assertAlmostEqual(float(workspace.nodes[node_id].custom_width or 0.0), off_width, places=6)

        self.scene.resize_node(node_id, off_width - 40.0, float(on_payload["height"]))
        payload_by_id = {item["node_id"]: item for item in self.scene.nodes_model}
        resized_payload = payload_by_id[node_id]

        self.assertAlmostEqual(resized_payload["surface_metrics"]["min_width"], on_min_width, places=6)
        self.assertAlmostEqual(resized_payload["width"], on_min_width, places=6)
        self.assertAlmostEqual(float(workspace.nodes[node_id].custom_width or 0.0), on_min_width, places=6)

    def test_default_sized_body_surface_nodes_display_with_content_safe_geometry(self) -> None:
        if self.registry.spec_or_none("tabular.input") is None:
            self.skipTest("tabular.input add-on is not registered in the default registry")

        node_id = self.scene.add_node_from_type("tabular.input", 40.0, 60.0)
        workspace = self.model.project.workspaces[self.workspace_id]
        node = workspace.nodes[node_id]
        node.custom_width = 210.0
        node.custom_height = 100.0

        self.scene.refresh_workspace_from_model(self.workspace_id)
        payload_by_id = {item["node_id"]: item for item in self.scene.nodes_model}
        clamped_payload = payload_by_id[node_id]

        self.assertGreater(float(clamped_payload["width"]), float(node.custom_width))
        self.assertGreater(float(clamped_payload["height"]), float(node.custom_height))
        self.assertGreaterEqual(float(clamped_payload["surface_metrics"]["body_height"]), 128.0)
        self.assertAlmostEqual(float(workspace.nodes[node_id].custom_width or 0.0), 210.0, places=6)
        self.assertAlmostEqual(float(workspace.nodes[node_id].custom_height or 0.0), 100.0, places=6)

        manual_width = float(clamped_payload["width"]) + 80.0
        manual_height = float(clamped_payload["height"]) + 50.0
        node.custom_width = manual_width
        node.custom_height = manual_height

        self.scene.refresh_workspace_from_model(self.workspace_id)
        payload_by_id = {item["node_id"]: item for item in self.scene.nodes_model}
        manual_payload = payload_by_id[node_id]

        self.assertAlmostEqual(float(manual_payload["width"]), manual_width, places=6)
        self.assertAlmostEqual(float(manual_payload["height"]), manual_height, places=6)
        self.assertAlmostEqual(float(workspace.nodes[node_id].custom_width or 0.0), manual_width, places=6)
        self.assertAlmostEqual(float(workspace.nodes[node_id].custom_height or 0.0), manual_height, places=6)

    def test_incompatible_edge_rejection_leaves_state_and_history_unchanged(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        source_id = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        target_id = self.scene.add_node_from_type("core.if", 320.0, 0.0)
        history.clear_workspace(self.workspace_id)
        workspace = self.model.active_workspace
        before = workspace.capture_snapshot()
        before_revision = workspace.mutation_revision

        with self.assertRaisesRegex(ValueError, "Incompatible data types"):
            self.scene.add_edge(source_id, "as_text", target_id, "condition")

        self.assertEqual(workspace.capture_snapshot(), before)
        self.assertEqual(workspace.mutation_revision, before_revision)
        self.assertEqual(history.undo_depth(self.workspace_id), 0)

    def test_bulk_edge_enable_rejects_mixed_invalid_batch_atomically(self) -> None:
        source_id = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        script_id = self.scene.add_node_from_type("core.python_script", 320.0, 0.0)
        branch_id = self.scene.add_node_from_type("core.if", 640.0, 0.0)
        valid = self.model._add_edge_record(
            self.workspace_id,
            source_node_id=source_id,
            source_port_key="value",
            target_node_id=script_id,
            target_port_key="payload",
            enabled=False,
            input_order=0,
        )
        invalid = self.model._add_edge_record(
            self.workspace_id,
            source_node_id=source_id,
            source_port_key="as_text",
            target_node_id=branch_id,
            target_port_key="condition",
            enabled=False,
            input_order=0,
        )
        self.scene.refresh_workspace_from_model(self.workspace_id)
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        history.clear_workspace(self.workspace_id)
        workspace = self.model.active_workspace
        before = workspace.capture_snapshot()
        before_revision = workspace.mutation_revision
        before_orders = {
            edge.edge_id: edge.input_order
            for edge in workspace.edges.values()
        }

        self.assertFalse(
            self.scene.set_edges_enabled(
                [valid.edge_id, invalid.edge_id],
                True,
            )
        )

        self.assertEqual(workspace.capture_snapshot(), before)
        self.assertEqual(workspace.mutation_revision, before_revision)
        self.assertEqual(
            {
                edge.edge_id: edge.input_order
                for edge in workspace.edges.values()
            },
            before_orders,
        )
        self.assertFalse(workspace.edges[valid.edge_id].enabled)
        self.assertFalse(workspace.edges[invalid.edge_id].enabled)
        self.assertEqual(history.undo_depth(self.workspace_id), 0)

    def test_style_mutations_update_payload_and_record_history(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        source_id = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        target_id = self.scene.add_node_from_type("core.python_script", 320.0, 40.0)
        passive_id = self.scene.add_node_from_type("passive.flowchart.process", 640.0, 80.0)
        edge_id = self.scene.add_edge(source_id, "value", target_id, "payload")
        history.clear_workspace(self.workspace_id)

        self.scene.set_node_visual_style(source_id, {"fill": "#102030", "badge": {"shape": "pill"}})
        self.assertEqual(history.undo_depth(self.workspace_id), 0)
        self.scene.set_node_visual_style(passive_id, {"fill": "#405060"})
        self.scene.set_edge_label(edge_id, "Primary path")
        self.scene.set_edge_visual_style(edge_id, {"stroke": "dashed", "arrow": {"kind": "none"}})

        self.assertEqual(history.undo_depth(self.workspace_id), 3)

        node_payload = {item["node_id"]: item for item in self.scene.nodes_model}
        edge_payload = {item["edge_id"]: item for item in self.scene.edges_model}
        self.assertNotIn("visual_style", node_payload[source_id])
        self.assertEqual(node_payload[passive_id]["visual_style"], {"fill": "#405060"})
        self.assertEqual(edge_payload[edge_id]["label"], "Primary path")
        self.assertEqual(
            edge_payload[edge_id]["visual_style"],
            {
                "stroke": "dashed",
                "arrow": {"kind": "none"},
                "display_mode": "default",
            },
        )

    def test_edge_display_modes_merge_style_history_and_reject_noops(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        workspace = self.model.project.workspaces[self.workspace_id]
        source_a = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        source_b = self.scene.add_node_from_type("core.constant", 0.0, 100.0)
        sink = self.scene.add_node_from_type("core.python_script", 320.0, 0.0)
        first = self.scene.add_edge(source_a, "value", sink, "payload")
        second = self.scene.add_edge(
            source_b, "value", sink, "payload", append_requested=True
        )
        self.scene.set_edge_visual_style(first, {"stroke_pattern": "dashed"})
        self.scene.set_edge_visual_style(second, {"arrow": {"kind": "none"}})
        history.clear_workspace(self.workspace_id)

        self.assertTrue(
            self.scene.set_edges_display_mode([second, first, second], "faint")
        )
        self.assertEqual(
            workspace.edges[first].visual_style,
            {"stroke_pattern": "dashed", "display_mode": "faint"},
        )
        self.assertEqual(
            workspace.edges[second].visual_style,
            {"arrow": {"kind": "none"}, "display_mode": "faint"},
        )
        self.assertEqual(history.undo_depth(self.workspace_id), 1)
        self.assertEqual(
            history._undo_stacks[self.workspace_id][-1].action_type,
            ACTION_EDIT_EDGE_STYLE,
        )
        self.assertIsNotNone(history.undo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertEqual(workspace.edges[first].visual_style, {"stroke_pattern": "dashed"})
        self.assertEqual(workspace.edges[second].visual_style, {"arrow": {"kind": "none"}})
        self.assertFalse(self.scene.set_edges_display_mode([first, second], "default"))
        self.assertTrue(
            all(
                "display_mode" not in workspace.edges[edge_id].visual_style
                for edge_id in (first, second)
            )
        )
        document = JsonProjectSerializer(self.registry).to_persistent_document(
            self.model.project
        )
        persisted_styles = {
            edge["edge_id"]: edge["visual_style"]
            for edge in document["workspaces"][0]["edges"]
        }
        self.assertNotIn("display_mode", persisted_styles[first])
        self.assertNotIn("display_mode", persisted_styles[second])
        self.assertEqual(history.undo_depth(self.workspace_id), 0)
        self.assertIsNotNone(history.redo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)

        history.clear_workspace(self.workspace_id)
        self.assertTrue(self.scene.set_edges_display_mode([first, second], "invalid"))
        self.assertTrue(
            all(
                "display_mode" not in workspace.edges[edge_id].visual_style
                for edge_id in (first, second)
            )
        )
        self.assertEqual(history.undo_depth(self.workspace_id), 1)
        self.assertFalse(self.scene.set_edges_display_mode([first, second], "default"))
        before = workspace.capture_snapshot()
        self.assertFalse(self.scene.set_edges_display_mode([first, "missing"], "hidden"))
        self.assertEqual(workspace.capture_snapshot(), before)
        self.assertEqual(history.undo_depth(self.workspace_id), 1)

    def test_validated_node_insertion_keeps_visual_style_only_for_passive_types(self) -> None:
        mutations = self.model.validated_mutations(self.workspace_id, self.registry)
        active = mutations.add_node(
            type_id="core.constant",
            title="Constant",
            x=0.0,
            y=0.0,
            visual_style={"fill": "#102030"},
        )
        passive = mutations.add_node(
            type_id="passive.flowchart.process",
            title="Process",
            x=240.0,
            y=0.0,
            visual_style={"fill": "#405060"},
        )

        self.assertEqual(active.visual_style, {})
        self.assertEqual(passive.visual_style, {"fill": "#405060"})

    def test_dataflow_authoring_mutations_follow_real_history_undo_redo(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        workspace = self.model.project.workspaces[self.workspace_id]
        source_a = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        source_b = self.scene.add_node_from_type("core.constant", 0.0, 100.0)
        source_c = self.scene.add_node_from_type("core.constant", 0.0, 200.0)
        sink = self.scene.add_node_from_type("core.python_script", 300.0, 0.0)

        def incoming_edges():
            return sorted(
                (
                    edge
                    for edge in workspace.edges.values()
                    if edge.target_node_id == sink and edge.target_port_key == "payload"
                ),
                key=lambda edge: edge.input_order,
            )

        def undo() -> None:
            self.assertIsNotNone(history.undo_workspace(self.workspace_id, workspace))
            self.scene.refresh_workspace_from_model(self.workspace_id)

        def redo() -> None:
            self.assertIsNotNone(history.redo_workspace(self.workspace_id, workspace))
            self.scene.refresh_workspace_from_model(self.workspace_id)

        first_edge = self.scene.add_edge(source_a, "value", sink, "payload")
        history.clear_workspace(self.workspace_id)
        replacement_edge = self.scene.add_edge(source_b, "value", sink, "payload")
        self.assertEqual([edge.source_node_id for edge in incoming_edges()], [source_b])
        undo()
        self.assertEqual([edge.edge_id for edge in incoming_edges()], [first_edge])
        redo()
        self.assertEqual([edge.edge_id for edge in incoming_edges()], [replacement_edge])

        history.clear_workspace(self.workspace_id)
        appended_edge = self.scene.add_edge(
            source_c,
            "value",
            sink,
            "payload",
            append_requested=True,
        )
        self.assertEqual(
            [(edge.source_node_id, edge.input_order) for edge in incoming_edges()],
            [(source_b, 0), (source_c, 1)],
        )
        undo()
        self.assertEqual([edge.edge_id for edge in incoming_edges()], [replacement_edge])
        redo()
        self.assertEqual(
            [edge.edge_id for edge in incoming_edges()],
            [replacement_edge, appended_edge],
        )

        history.clear_workspace(self.workspace_id)
        self.assertTrue(self.scene.set_edge_enabled(replacement_edge, False))
        self.assertFalse(workspace.edges[replacement_edge].enabled)
        undo()
        self.assertTrue(workspace.edges[replacement_edge].enabled)
        redo()
        self.assertFalse(workspace.edges[replacement_edge].enabled)

        history.clear_workspace(self.workspace_id)
        self.assertTrue(self.scene.set_edge_enabled(replacement_edge, True))
        undo()
        self.assertFalse(workspace.edges[replacement_edge].enabled)
        redo()
        self.assertTrue(workspace.edges[replacement_edge].enabled)

        history.clear_workspace(self.workspace_id)
        self.assertTrue(
            self.scene.set_port_modifiers(sink, "payload", ["clean", "graft"])
        )
        self.assertEqual(
            workspace.nodes[sink].port_modifiers,
            {"payload": ("graft", "clean")},
        )
        undo()
        self.assertEqual(workspace.nodes[sink].port_modifiers, {})
        redo()
        self.assertEqual(
            workspace.nodes[sink].port_modifiers,
            {"payload": ("graft", "clean")},
        )

        history.clear_workspace(self.workspace_id)
        self.assertTrue(self.scene.set_principal_input_port(sink, "payload"))
        self.assertEqual(workspace.nodes[sink].principal_input_port_id, "payload")
        undo()
        self.assertIsNone(workspace.nodes[sink].principal_input_port_id)
        redo()
        self.assertEqual(workspace.nodes[sink].principal_input_port_id, "payload")

        gate = self.scene.add_node_from_type("core.stream_gate", 600.0, 0.0)
        gate_sink = self.scene.add_node_from_type("core.python_script", 900.0, 0.0)
        inserted_port = self.scene.insert_dynamic_port(gate, "outputs", 1)
        gate_edge = self.scene.add_edge(gate, inserted_port, gate_sink, "payload")
        history.clear_workspace(self.workspace_id)

        removal = self.scene.remove_dynamic_port(gate, "outputs", inserted_port)
        self.assertEqual(removal["port_key"], inserted_port)
        self.assertEqual(removal["removed_edge_ids"], [gate_edge])
        self.assertNotIn(gate_edge, workspace.edges)
        self.assertEqual(
            workspace.nodes[gate].properties["output_port_ids"],
            ["output_0", "output_1"],
        )
        undo()
        self.assertIn(gate_edge, workspace.edges)
        self.assertEqual(
            workspace.nodes[gate].properties["output_port_ids"],
            ["output_0", inserted_port, "output_1"],
        )
        redo()
        self.assertNotIn(gate_edge, workspace.edges)
        self.assertEqual(
            workspace.nodes[gate].properties["output_port_ids"],
            ["output_0", "output_1"],
        )

    def test_move_edge_source_preserves_identity_metadata_order_and_one_history_entry(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        workspace = self.model.project.workspaces[self.workspace_id]
        source_a = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        source_b = self.scene.add_node_from_type("core.constant", 0.0, 100.0)
        source_c = self.scene.add_node_from_type("core.constant", 0.0, 200.0)
        sink = self.scene.add_node_from_type("core.python_script", 300.0, 0.0)
        edge_id = self.scene.add_edge(source_a, "value", sink, "payload")
        sibling_id = self.scene.add_edge(
            source_c, "value", sink, "payload", append_requested=True
        )
        self.scene.set_edge_label(edge_id, "Primary")
        self.scene.set_edge_visual_style(edge_id, {"stroke_pattern": "dashed"})
        self.scene.set_edge_enabled(edge_id, False)
        history.clear_workspace(self.workspace_id)

        self.assertTrue(
            self.scene.request_rewire_edges(
                [edge_id],
                "source",
                source_b,
                "value",
                copy_requested=False,
                append_requested=False,
            )
        )

        moved = workspace.edges[edge_id]
        self.assertEqual(moved.source_node_id, source_b)
        self.assertEqual(moved.input_order, 0)
        self.assertFalse(moved.enabled)
        self.assertEqual(moved.label, "Primary")
        self.assertEqual(moved.visual_style, {"stroke_pattern": "dashed"})
        self.assertEqual(workspace.edges[sibling_id].input_order, 1)
        self.assertEqual(len(history._undo_stacks[self.workspace_id]), 1)
        self.assertEqual(
            history._undo_stacks[self.workspace_id][-1].action_type,
            ACTION_ADD_EDGE,
        )
        self.assertIsNotNone(history.undo_workspace(self.workspace_id, workspace))
        self.assertEqual(workspace.edges[edge_id].source_node_id, source_a)

    def test_move_edge_target_replace_append_cancel_and_disconnect_are_atomic(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        workspace = self.model.project.workspaces[self.workspace_id]
        source_a = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        source_b = self.scene.add_node_from_type("core.constant", 0.0, 100.0)
        source_c = self.scene.add_node_from_type("core.constant", 0.0, 200.0)
        sink_a = self.scene.add_node_from_type("core.python_script", 300.0, 0.0)
        sink_b = self.scene.add_node_from_type("core.python_script", 300.0, 120.0)
        edge_id = self.scene.add_edge(source_a, "value", sink_a, "payload")
        replaced_id = self.scene.add_edge(source_b, "value", sink_b, "payload")
        history.clear_workspace(self.workspace_id)

        self.assertTrue(
            self.scene.request_rewire_edges(
                [edge_id],
                "target",
                sink_b,
                "payload",
                copy_requested=False,
                append_requested=False,
            )
        )
        self.assertIn(edge_id, workspace.edges)
        self.assertNotIn(replaced_id, workspace.edges)
        self.assertEqual(workspace.edges[edge_id].input_order, 0)
        self.assertEqual(len(history._undo_stacks[self.workspace_id]), 1)
        self.assertIsNotNone(history.undo_workspace(self.workspace_id, workspace))
        self.assertIn(replaced_id, workspace.edges)
        self.assertEqual(workspace.edges[edge_id].target_node_id, sink_a)

        history.clear_workspace(self.workspace_id)
        appended_target_edge = self.scene.add_edge(
            source_c, "value", sink_b, "payload", append_requested=True
        )
        history.clear_workspace(self.workspace_id)
        self.assertTrue(
            self.scene.request_rewire_edges(
                [edge_id],
                "target",
                sink_b,
                "payload",
                copy_requested=False,
                append_requested=True,
            )
        )
        self.assertEqual(workspace.edges[appended_target_edge].input_order, 1)
        self.assertEqual(workspace.edges[edge_id].input_order, 2)

        history.clear_workspace(self.workspace_id)
        self.assertFalse(
            self.scene.request_rewire_edges(
                [edge_id],
                "target",
                sink_b,
                "payload",
                copy_requested=False,
                append_requested=False,
            )
        )
        self.assertEqual(history._undo_stacks.get(self.workspace_id, []), [])
        self.assertFalse(
            self.scene.request_rewire_edges(
                [edge_id],
                "source",
                source_c,
                "value",
                copy_requested=False,
                append_requested=False,
            )
        )
        self.assertIn(edge_id, workspace.edges)
        self.assertEqual(history._undo_stacks.get(self.workspace_id, []), [])

        self.assertFalse(
            self.scene.request_rewire_edges(
                [edge_id],
                "target",
                source_a,
                "value",
                copy_requested=False,
                append_requested=False,
            )
        )
        self.assertEqual(workspace.edges[edge_id].target_node_id, sink_b)
        self.assertEqual(history._undo_stacks.get(self.workspace_id, []), [])

        self.assertTrue(
            self.scene.request_rewire_edges(
                [edge_id],
                "target",
                "",
                "",
                copy_requested=False,
                append_requested=False,
            )
        )
        self.assertNotIn(edge_id, workspace.edges)
        self.assertEqual(len(history._undo_stacks[self.workspace_id]), 1)
        self.assertEqual(
            history._undo_stacks[self.workspace_id][-1].action_type,
            ACTION_REMOVE_EDGE,
        )
        self.assertIsNotNone(history.undo_workspace(self.workspace_id, workspace))
        self.assertIn(edge_id, workspace.edges)

    def test_request_rewire_edges_moves_and_disconnects_a_bundle_atomically(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        workspace = self.model.project.workspaces[self.workspace_id]
        source_a = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        source_b = self.scene.add_node_from_type("core.constant", 0.0, 100.0)
        sink_a = self.scene.add_node_from_type("core.python_script", 320.0, 0.0)
        sink_b = self.scene.add_node_from_type("core.python_script", 640.0, 0.0)
        first = self.scene.add_edge(source_a, "value", sink_a, "payload")
        second = self.scene.add_edge(
            source_b, "value", sink_a, "payload", append_requested=True
        )
        self.scene.set_edge_label(first, "Primary")
        self.scene.set_edge_visual_style(first, {"stroke_pattern": "dashed"})
        self.scene.set_edge_enabled(first, False)
        history.clear_workspace(self.workspace_id)

        self.assertTrue(
            self.scene.request_rewire_edges(
                [second, first], "target", sink_b, "payload"
            )
        )
        self.assertEqual(
            [
                (edge.edge_id, edge.source_node_id, edge.input_order)
                for edge in sorted(
                    (
                        edge
                        for edge in workspace.edges.values()
                        if edge.target_node_id == sink_b
                    ),
                    key=lambda edge: edge.input_order,
                )
            ],
            [(first, source_a, 0), (second, source_b, 1)],
        )
        self.assertFalse(workspace.edges[first].enabled)
        self.assertEqual(workspace.edges[first].label, "Primary")
        self.assertEqual(
            workspace.edges[first].visual_style, {"stroke_pattern": "dashed"}
        )
        self.assertEqual(history.undo_depth(self.workspace_id), 1)
        self.assertIsNotNone(history.undo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertEqual(workspace.edges[first].target_node_id, sink_a)
        self.assertEqual(workspace.edges[second].target_node_id, sink_a)
        self.assertIsNotNone(history.redo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertEqual(workspace.edges[first].target_node_id, sink_b)
        self.assertEqual(workspace.edges[second].target_node_id, sink_b)

        history.clear_workspace(self.workspace_id)
        self.assertTrue(
            self.scene.request_rewire_edges([first, second], "target", "", "")
        )
        self.assertNotIn(first, workspace.edges)
        self.assertNotIn(second, workspace.edges)
        self.assertEqual(history.undo_depth(self.workspace_id), 1)
        self.assertIsNotNone(history.undo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertEqual(workspace.edges[first].target_node_id, sink_b)
        self.assertEqual(workspace.edges[second].target_node_id, sink_b)

    def test_request_rewire_edges_rejects_mixed_duplicate_and_incompatible_batches(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        workspace = self.model.project.workspaces[self.workspace_id]
        source_a = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        source_b = self.scene.add_node_from_type("core.constant", 0.0, 100.0)
        sink = self.scene.add_node_from_type("core.python_script", 320.0, 0.0)
        branch = self.scene.add_node_from_type("core.if", 640.0, 0.0)
        first = self.scene.add_edge(source_a, "value", sink, "payload")
        second = self.scene.add_edge(
            source_b, "value", sink, "payload", append_requested=True
        )
        text_edge = self.scene.add_edge(
            source_a, "as_text", sink, "payload", append_requested=True
        )
        history.clear_workspace(self.workspace_id)
        before = workspace.capture_snapshot()

        self.assertFalse(
            self.scene.request_rewire_edges(
                [first, second], "source", source_b, "value"
            )
        )
        self.assertEqual(workspace.capture_snapshot(), before)
        self.assertFalse(
            self.scene.request_rewire_edges(
                [first, text_edge], "target", branch, "condition"
            )
        )
        self.assertEqual(workspace.capture_snapshot(), before)
        self.assertFalse(
            self.scene.request_rewire_edges(
                [first, second], "target", sink, "payload", copy_requested=True
            )
        )
        self.assertEqual(workspace.capture_snapshot(), before)
        self.assertEqual(history.undo_depth(self.workspace_id), 0)

    def test_rewire_compatibility_snapshot_intersects_the_whole_bundle(self) -> None:
        string_source = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        number_source = self.scene.add_node_from_type("data.number_slider", 0.0, 120.0)
        shared_sink = self.scene.add_node_from_type("core.python_script", 320.0, 0.0)
        other_sink = self.scene.add_node_from_type("core.python_script", 320.0, 160.0)
        string_target = self.scene.add_node_from_type("core.logger", 640.0, 0.0)
        number_target = self.scene.add_node_from_type("core.stream_gate", 640.0, 120.0)
        common_target = self.scene.add_node_from_type("core.python_script", 640.0, 240.0)
        duplicate_target = self.scene.add_node_from_type("core.python_script", 640.0, 480.0)
        string_edge = self.scene.add_edge(
            string_source, "as_text", shared_sink, "payload"
        )
        number_edge = self.scene.add_edge(
            number_source,
            "value",
            shared_sink,
            "payload",
            append_requested=True,
        )
        other_number_edge = self.scene.add_edge(
            number_source, "value", other_sink, "payload"
        )
        self.scene.add_edge(string_source, "as_text", duplicate_target, "payload")

        def endpoint_ids(edge_ids: list[str]) -> set[tuple[str, str]]:
            snapshot = self.scene.policy_bridge.compatible_rewire_endpoint_snapshot(
                edge_ids, "target"
            )
            self.assertEqual(snapshot["candidate_role"], "target")
            self.assertEqual(
                snapshot["catalog_generation"], self.registry.data_types.fingerprint()
            )
            return {
                (item["node_id"], item["port_key"])
                for item in snapshot["compatible_endpoint_ids"]
            }

        string_candidates = endpoint_ids([string_edge])
        number_candidates = endpoint_ids([number_edge])
        bundle_candidates = endpoint_ids([number_edge, string_edge])
        self.assertIn((string_target, "message"), string_candidates)
        self.assertIn((number_target, "gate"), number_candidates)
        self.assertIn((common_target, "payload"), bundle_candidates)
        self.assertNotIn((string_target, "message"), bundle_candidates)
        self.assertNotIn((number_target, "gate"), bundle_candidates)
        self.assertNotIn((duplicate_target, "payload"), bundle_candidates)
        self.assertEqual(endpoint_ids([string_edge, "missing"]), set())
        self.assertEqual(endpoint_ids([string_edge, other_number_edge]), set())

    def test_request_rewire_edges_copies_one_selected_edge_with_one_history_entry(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        workspace = self.model.project.workspaces[self.workspace_id]
        source_a = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        source_b = self.scene.add_node_from_type("core.constant", 0.0, 100.0)
        source_c = self.scene.add_node_from_type("core.constant", 0.0, 200.0)
        sink_a = self.scene.add_node_from_type("core.python_script", 320.0, 0.0)
        sink_b = self.scene.add_node_from_type("core.python_script", 640.0, 0.0)
        first = self.scene.add_edge(source_a, "value", sink_a, "payload")
        second = self.scene.add_edge(
            source_b, "value", sink_a, "payload", append_requested=True
        )
        existing = self.scene.add_edge(source_c, "value", sink_b, "payload")
        self.scene.set_edge_label(first, "Primary")
        self.scene.set_edge_visual_style(first, {"stroke_pattern": "dashed"})
        self.scene.set_edge_enabled(first, False)
        history.clear_workspace(self.workspace_id)

        self.assertTrue(
            self.scene.request_rewire_edges(
                [first], "target", sink_b, "payload", copy_requested=True
            )
        )
        copied = sorted(
            (
                edge
                for edge in workspace.edges.values()
                if edge.target_node_id == sink_b
            ),
            key=lambda edge: edge.input_order,
        )
        self.assertEqual(len(copied), 2)
        self.assertEqual(copied[0].edge_id, existing)
        copied_first = copied[1]
        self.assertNotEqual(copied_first.edge_id, first)
        self.assertEqual(
            [(edge.source_node_id, edge.input_order) for edge in copied],
            [(source_c, 0), (source_a, 1)],
        )
        self.assertFalse(copied_first.enabled)
        self.assertEqual(copied_first.label, "Primary")
        self.assertEqual(copied_first.visual_style, {"stroke_pattern": "dashed"})
        self.assertEqual(history.undo_depth(self.workspace_id), 1)
        copied_ids = {edge.edge_id for edge in copied}
        self.assertIsNotNone(history.undo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertEqual(
            {edge.edge_id for edge in workspace.edges.values() if edge.target_node_id == sink_b},
            {existing},
        )
        self.assertIn(first, workspace.edges)
        self.assertIn(second, workspace.edges)
        self.assertIsNotNone(history.redo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertEqual(
            {edge.edge_id for edge in workspace.edges.values() if edge.target_node_id == sink_b},
            copied_ids,
        )

    def test_propagate_passive_node_style_flood_fills_connected_component_with_undo_redo(self) -> None:
        workspace = self.model.project.workspaces[self.workspace_id]
        node_ids = [
            self.scene.add_node_from_type("passive.flowchart.process", float(index * 24), 40.0)
            for index in range(100)
        ]
        passthrough_id = self.scene.add_node_from_type("tests.track_b_flowchart_passthrough", 2500.0, 40.0)
        beyond_passthrough_id = self.scene.add_node_from_type("passive.flowchart.decision", 2720.0, 40.0)
        disconnected_planning_id = self.scene.add_node_from_type("passive.planning.task_card", 3000.0, 240.0)
        for left_id, right_id in zip(node_ids, node_ids[1:]):
            self.model.add_edge(self.workspace_id, left_id, "right", right_id, "left")
        self.model.add_edge(self.workspace_id, node_ids[-1], "bottom", node_ids[0], "top")
        self.model.add_edge(self.workspace_id, node_ids[50], "right", passthrough_id, "left")
        self.model.add_edge(self.workspace_id, passthrough_id, "right", beyond_passthrough_id, "left")
        self.scene.refresh_workspace_from_model(self.workspace_id)

        source_style = {
            "fill_color": "#00CEC9",
            "border_color": "#0984E3",
            "text_color": "#2D3436",
            "border_width": 3.0,
        }
        old_target_style = {"fill_color": "#FFEAA7", "border_width": 1.0}
        disconnected_planning_style = {"fill_color": "#FAB1A0"}
        workspace.nodes[node_ids[2]].visual_style = dict(source_style)
        workspace.nodes[node_ids[0]].visual_style = dict(old_target_style)
        workspace.nodes[node_ids[-1]].visual_style = dict(old_target_style)
        workspace.nodes[beyond_passthrough_id].visual_style = dict(old_target_style)
        workspace.nodes[passthrough_id].visual_style = {"fill_color": "#D63031"}
        workspace.nodes[disconnected_planning_id].visual_style = dict(disconnected_planning_style)

        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        history.clear_workspace(self.workspace_id)

        self.assertTrue(self.scene.propagate_passive_node_style(node_ids[2]))
        self.assertEqual(history.undo_depth(self.workspace_id), 1)
        self.assertEqual(history.redo_depth(self.workspace_id), 0)
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_EDIT_NODE_STYLE)

        for candidate_id in node_ids:
            self.assertEqual(workspace.nodes[candidate_id].visual_style, source_style)
        self.assertEqual(workspace.nodes[beyond_passthrough_id].visual_style, source_style)
        self.assertEqual(workspace.nodes[passthrough_id].visual_style, {"fill_color": "#D63031"})
        self.assertEqual(workspace.nodes[disconnected_planning_id].visual_style, disconnected_planning_style)

        undo_entry = history.undo_workspace(self.workspace_id, workspace)
        self.assertIsNotNone(undo_entry)
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertEqual(history.undo_depth(self.workspace_id), 0)
        self.assertEqual(history.redo_depth(self.workspace_id), 1)
        self.assertEqual(workspace.nodes[node_ids[2]].visual_style, source_style)
        self.assertEqual(workspace.nodes[node_ids[0]].visual_style, old_target_style)
        self.assertEqual(workspace.nodes[node_ids[-1]].visual_style, old_target_style)
        self.assertEqual(workspace.nodes[beyond_passthrough_id].visual_style, old_target_style)
        self.assertEqual(workspace.nodes[disconnected_planning_id].visual_style, disconnected_planning_style)

        redo_entry = history.redo_workspace(self.workspace_id, workspace)
        self.assertIsNotNone(redo_entry)
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertEqual(history.undo_depth(self.workspace_id), 1)
        self.assertEqual(history.redo_depth(self.workspace_id), 0)
        self.assertEqual(workspace.nodes[node_ids[0]].visual_style, source_style)
        self.assertEqual(workspace.nodes[node_ids[-1]].visual_style, source_style)
        self.assertEqual(workspace.nodes[beyond_passthrough_id].visual_style, source_style)
        self.assertEqual(workspace.nodes[disconnected_planning_id].visual_style, disconnected_planning_style)

    def test_propagate_passive_node_style_empty_source_clears_connected_targets(self) -> None:
        workspace = self.model.project.workspaces[self.workspace_id]
        source_id = self.scene.add_node_from_type("passive.flowchart.process", 20.0, 40.0)
        target_id = self.scene.add_node_from_type("passive.flowchart.decision", 260.0, 40.0)
        disconnected_planning_id = self.scene.add_node_from_type("passive.planning.task_card", 500.0, 40.0)
        self.scene.add_edge(source_id, "right", target_id, "left")
        workspace.nodes[target_id].visual_style = {"fill_color": "#FFEAA7", "border_width": 2.0}
        workspace.nodes[disconnected_planning_id].visual_style = {"fill_color": "#FAB1A0"}

        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        history.clear_workspace(self.workspace_id)

        self.assertTrue(self.scene.propagate_passive_node_style(source_id))
        self.assertEqual(workspace.nodes[source_id].visual_style, {})
        self.assertEqual(workspace.nodes[target_id].visual_style, {})
        self.assertEqual(workspace.nodes[disconnected_planning_id].visual_style, {"fill_color": "#FAB1A0"})
        self.assertEqual(history.undo_depth(self.workspace_id), 1)

    def test_flowchart_scene_payloads_publish_family_metrics_and_shape_aware_anchors(self) -> None:
        source_id = self.scene.add_node_from_type("tests.track_b_flowchart_decision", 20.0, 30.0)
        target_id = self.scene.add_node_from_type("tests.track_b_flowchart_connector", 360.0, 90.0)
        edge_id = self.scene.add_edge(source_id, "right", target_id, "left")

        node_payload = {item["node_id"]: item for item in self.scene.nodes_model}
        edge_payload = {item["edge_id"]: item for item in self.scene.edges_model}[edge_id]
        source_payload = node_payload[source_id]

        self.assertEqual(source_payload["surface_family"], "flowchart")
        self.assertEqual(source_payload["surface_variant"], "decision")
        self.assertFalse(bool(source_payload["surface_metrics"]["use_host_chrome"]))
        self.assertTrue(bool(source_payload["surface_metrics"]["title_centered"]))
        self.assertGreaterEqual(source_payload["surface_metrics"]["min_height"], 120.0)
        self.assertGreaterEqual(source_payload["width"], 220.0)
        self.assertEqual(edge_payload["source_port_side"], "right")
        self.assertEqual(edge_payload["target_port_side"], "left")
        self.assertAlmostEqual(edge_payload["sx"], source_payload["x"] + source_payload["width"] - 0.5, places=4)
        self.assertAlmostEqual(edge_payload["sy"], source_payload["y"] + source_payload["height"] * 0.5, places=4)

    def test_builtin_flowchart_catalog_nodes_keep_display_titles_and_cardinal_neutral_ports(self) -> None:
        decision_id = self.scene.add_node_from_type("passive.flowchart.decision", 20.0, 30.0)
        end_id = self.scene.add_node_from_type("passive.flowchart.end", 360.0, 90.0)
        edge_id = self.scene.add_edge(decision_id, "right", end_id, "left")

        workspace = self.model.project.workspaces[self.workspace_id]
        self.assertEqual(workspace.nodes[decision_id].title, "Decision")
        self.assertEqual(workspace.nodes[end_id].title, "End")

        node_payload = {item["node_id"]: item for item in self.scene.nodes_model}
        edge_payload = {item["edge_id"]: item for item in self.scene.edges_model}[edge_id]
        decision_ports = {port["key"]: port for port in node_payload[decision_id]["ports"]}

        self.assertEqual(set(decision_ports), {"top", "right", "bottom", "left"})
        self.assertTrue(all(port["direction"] == "neutral" for port in decision_ports.values()))
        self.assertEqual(decision_ports["right"]["label"], "right")
        self.assertEqual(decision_ports["left"]["label"], "left")
        self.assertEqual(decision_ports["right"]["kind"], "flow")
        self.assertEqual(decision_ports["left"]["data_type"], "flow")
        self.assertEqual(edge_payload["source_port_kind"], "flow")
        self.assertEqual(edge_payload["target_port_kind"], "flow")

    def test_connect_nodes_selects_facing_cardinal_ports_for_neutral_flowchart_nodes(self) -> None:
        horizontal_source_id = self.scene.add_node_from_type("passive.flowchart.process", 20.0, 30.0)
        horizontal_target_id = self.scene.add_node_from_type("passive.flowchart.process", 360.0, 90.0)
        vertical_source_id = self.scene.add_node_from_type("passive.flowchart.process", 720.0, 40.0)
        vertical_target_id = self.scene.add_node_from_type("passive.flowchart.process", 720.0, 320.0)

        horizontal_edge_id = self.scene.connect_nodes(horizontal_source_id, horizontal_target_id)
        vertical_edge_id = self.scene.connect_nodes(vertical_source_id, vertical_target_id)

        workspace = self.model.project.workspaces[self.workspace_id]
        horizontal_edge = workspace.edges[horizontal_edge_id]
        vertical_edge = workspace.edges[vertical_edge_id]

        self.assertEqual(horizontal_edge.source_node_id, horizontal_source_id)
        self.assertEqual(horizontal_edge.source_port_key, "right")
        self.assertEqual(horizontal_edge.target_node_id, horizontal_target_id)
        self.assertEqual(horizontal_edge.target_port_key, "left")
        self.assertEqual(vertical_edge.source_node_id, vertical_source_id)
        self.assertEqual(vertical_edge.source_port_key, "bottom")
        self.assertEqual(vertical_edge.target_node_id, vertical_target_id)
        self.assertEqual(vertical_edge.target_port_key, "top")

    def test_connect_nodes_selects_facing_cardinal_ports_for_non_flowchart_passive_nodes(self) -> None:
        planning_source_id = self.scene.add_node_from_type("passive.planning.task_card", 20.0, 30.0)
        planning_target_id = self.scene.add_node_from_type("passive.planning.task_card", 360.0, 90.0)
        note_source_id = self.scene.add_node_from_type("passive.annotation.sticky_note", 720.0, 40.0)
        note_target_id = self.scene.add_node_from_type("passive.annotation.sticky_note", 720.0, 320.0)

        planning_edge_id = self.scene.connect_nodes(planning_source_id, planning_target_id)
        note_edge_id = self.scene.connect_nodes(note_source_id, note_target_id)

        workspace = self.model.project.workspaces[self.workspace_id]
        planning_edge = workspace.edges[planning_edge_id]
        note_edge = workspace.edges[note_edge_id]

        self.assertEqual(planning_edge.source_node_id, planning_source_id)
        self.assertEqual(planning_edge.source_port_key, "right")
        self.assertEqual(planning_edge.target_node_id, planning_target_id)
        self.assertEqual(planning_edge.target_port_key, "left")
        self.assertEqual(note_edge.source_node_id, note_source_id)
        self.assertEqual(note_edge.source_port_key, "bottom")
        self.assertEqual(note_edge.target_node_id, note_target_id)
        self.assertEqual(note_edge.target_port_key, "top")

    def test_non_flowchart_passive_edge_payloads_publish_cardinal_side_metadata(self) -> None:
        source_id = self.scene.add_node_from_type("passive.planning.task_card", 20.0, 30.0)
        target_id = self.scene.add_node_from_type(
            "passive.media.mail_panel", 360.0, 90.0
        )
        edge_id = self.scene.add_edge(source_id, "right", target_id, "left")

        node_payload = {item["node_id"]: item for item in self.scene.nodes_model}
        edge_payload = {item["edge_id"]: item for item in self.scene.edges_model}[edge_id]

        self.assertEqual(node_payload[source_id]["surface_family"], "planning")
        self.assertEqual(node_payload[target_id]["surface_family"], "media")
        self.assertEqual(edge_payload["source_port_side"], "right")
        self.assertEqual(edge_payload["target_port_side"], "left")

    def test_connect_ports_reverses_stored_flowchart_arrow_when_neutral_click_order_reverses(self) -> None:
        forward_source_id = self.scene.add_node_from_type("passive.flowchart.process", 20.0, 30.0)
        forward_target_id = self.scene.add_node_from_type("passive.flowchart.process", 360.0, 90.0)
        reverse_source_id = self.scene.add_node_from_type("passive.flowchart.process", 720.0, 40.0)
        reverse_target_id = self.scene.add_node_from_type("passive.flowchart.process", 1060.0, 120.0)

        interactions = GraphInteractions(self.scene, self.registry)
        self.assertTrue(interactions.connect_ports(forward_source_id, "right", forward_target_id, "left").ok)
        self.assertTrue(interactions.connect_ports(reverse_target_id, "left", reverse_source_id, "right").ok)

        workspace = self.model.project.workspaces[self.workspace_id]
        edge_by_source_target = {
            (edge.source_node_id, edge.target_node_id): edge
            for edge in workspace.edges.values()
        }
        forward_edge = edge_by_source_target[(forward_source_id, forward_target_id)]
        reverse_edge = edge_by_source_target[(reverse_target_id, reverse_source_id)]

        self.assertEqual(forward_edge.source_port_key, "right")
        self.assertEqual(forward_edge.target_port_key, "left")
        self.assertEqual(reverse_edge.source_port_key, "left")
        self.assertEqual(reverse_edge.target_port_key, "right")

    def test_connect_ports_rejects_same_node_flowchart_flow_edge(self) -> None:
        node_id = self.scene.add_node_from_type("passive.flowchart.process", 20.0, 30.0)

        interactions = GraphInteractions(self.scene, self.registry)
        result = interactions.connect_ports(node_id, "right", node_id, "bottom")

        self.assertFalse(result.ok)
        self.assertEqual(result.message, "Flow edges cannot connect ports on the same node.")
        workspace = self.model.project.workspaces[self.workspace_id]
        self.assertEqual(len(workspace.edges), 0)

    def test_planning_and_annotation_scene_payloads_publish_properties_and_keep_titles_synced(self) -> None:
        task_id = self.scene.add_node_from_type("passive.planning.task_card", 40.0, 60.0)
        note_id = self.scene.add_node_from_type("passive.annotation.sticky_note", 340.0, 80.0)
        text_id = self.scene.add_node_from_type("passive.annotation.text", 640.0, 90.0)

        self.scene.set_node_property(task_id, "title", "Ship parser")
        self.scene.set_node_property(task_id, "body", "Finalize validation and release notes.")
        self.scene.set_node_property(task_id, "body_format", "markdown")
        self.scene.set_node_property(task_id, "body_font_size", 19)
        self.scene.set_node_property(task_id, "owner", "Platform")
        self.scene.set_node_property(task_id, "due_date", "2026-03-31")
        self.scene.set_node_property(task_id, "status", "in_progress")
        self.scene.set_node_title(note_id, "Release note")
        self.scene.set_node_property(note_id, "body", "Track follow-up messaging for the rollout.")
        self.scene.set_node_property(text_id, "text", "**Bare** text")
        self.scene.set_node_property(text_id, "font_size", 22)
        self.scene.set_node_property(text_id, "text_color", "#AABBCC")
        self.scene.set_node_property(text_id, "horizontal_alignment", "center")

        workspace = self.model.project.workspaces[self.workspace_id]
        node_payload = {item["node_id"]: item for item in self.scene.nodes_model}
        task_payload = node_payload[task_id]
        note_payload = node_payload[note_id]
        text_payload = node_payload[text_id]

        self.assertEqual(workspace.nodes[task_id].title, "Ship parser")
        self.assertEqual(workspace.nodes[note_id].title, "Release note")
        self.assertEqual(workspace.nodes[note_id].properties["title"], "Release note")

        self.assertEqual(task_payload["surface_family"], "planning")
        self.assertEqual(task_payload["surface_variant"], "task_card")
        self.assertEqual(task_payload["title"], "Ship parser")
        self.assertEqual(task_payload["properties"]["body_format"], "markdown")
        self.assertEqual(task_payload["properties"]["body_font_size"], 19)
        self.assertEqual(task_payload["properties"]["owner"], "Platform")
        self.assertEqual(task_payload["properties"]["status"], "in_progress")
        self.assertGreaterEqual(task_payload["surface_metrics"]["min_height"], 148.0)
        self.assertTrue(bool(task_payload["surface_metrics"]["use_host_chrome"]))
        self.assertEqual(note_payload["surface_family"], "annotation")
        self.assertEqual(note_payload["surface_variant"], "sticky_note")
        self.assertEqual(note_payload["title"], "Release note")
        self.assertEqual(note_payload["properties"]["body"], "Track follow-up messaging for the rollout.")
        self.assertGreaterEqual(note_payload["surface_metrics"]["min_width"], 176.0)
        self.assertEqual(text_payload["surface_family"], "annotation")
        self.assertEqual(text_payload["surface_variant"], "text")
        self.assertEqual(text_payload["surface_spec"]["component_key"], "annotation_text")
        self.assertEqual(text_payload["properties"]["text"], "**Bare** text")
        self.assertEqual(text_payload["properties"]["font_size"], 22)
        self.assertEqual(text_payload["properties"]["text_color"], "#AABBCC")
        self.assertFalse(bool(text_payload["surface_metrics"]["use_host_chrome"]))
        self.assertFalse(bool(text_payload["surface_metrics"]["use_host_shadow"]))
        self.assertNotIn("show_header_background", text_payload["surface_metrics"])
        self.assertNotIn("show_accent_bar", text_payload["surface_metrics"])
        self.assertEqual([port["key"] for port in text_payload["ports"]], ["top", "right", "bottom", "left"])

    def test_batch_title_updates_keep_titles_synced_for_passive_nodes_and_canonical_for_standard_and_subnode_nodes(self) -> None:
        task_id = self.scene.add_node_from_type("passive.planning.task_card", 40.0, 60.0)
        logger_id = self.scene.add_node_from_type("core.logger", 340.0, 80.0)
        shell_id = self.scene.add_node_from_type("core.subnode", 640.0, 100.0)

        self.assertFalse(self.scene.set_node_properties(shell_id, {"title": "   "}))
        self.assertTrue(
            self.scene.set_node_properties(
                task_id,
                {
                    "title": "Ship parser",
                    "owner": "Platform",
                },
            )
        )
        self.assertTrue(
            self.scene.set_node_properties(
                logger_id,
                {
                    "title": "Primary Logger",
                    "message": "Updated from batch",
                },
            )
        )
        self.assertTrue(self.scene.set_node_properties(shell_id, {"title": "Nested Workflow"}))

        workspace = self.model.project.workspaces[self.workspace_id]
        node_payload = {item["node_id"]: item for item in self.scene.nodes_model}

        task_node = workspace.nodes[task_id]
        logger_node = workspace.nodes[logger_id]
        shell_node = workspace.nodes[shell_id]

        self.assertEqual(task_node.title, "Ship parser")
        self.assertEqual(task_node.properties["title"], "Ship parser")
        self.assertEqual(task_node.properties["owner"], "Platform")
        self.assertEqual(logger_node.title, "Primary Logger")
        self.assertEqual(logger_node.properties["message"], "Updated from batch")
        self.assertNotIn("title", logger_node.properties)
        self.assertEqual(shell_node.title, "Nested Workflow")
        self.assertNotIn("title", shell_node.properties)

        self.assertEqual(node_payload[task_id]["title"], "Ship parser")
        self.assertEqual(node_payload[task_id]["properties"]["title"], "Ship parser")
        self.assertEqual(node_payload[logger_id]["title"], "Primary Logger")
        self.assertNotIn("title", node_payload[logger_id]["properties"])
        self.assertEqual(node_payload[shell_id]["title"], "Nested Workflow")
        self.assertNotIn("title", node_payload[shell_id]["properties"])

    def test_title_property_mutations_use_rename_history_for_single_title_and_property_history_for_batches(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        node_id = self.scene.add_node_from_type("core.logger", 40.0, 60.0)
        history.clear_workspace(self.workspace_id)

        self.scene.set_node_property(node_id, "title", "Logger Alpha")

        self.assertEqual(history.undo_depth(self.workspace_id), 1)
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_RENAME_NODE)
        history.clear_workspace(self.workspace_id)

        self.assertTrue(self.scene.set_node_properties(node_id, {"title": "Logger Beta"}))

        self.assertEqual(history.undo_depth(self.workspace_id), 1)
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_RENAME_NODE)
        history.clear_workspace(self.workspace_id)

        self.assertTrue(
            self.scene.set_node_properties(
                node_id,
                {
                    "title": "Logger Gamma",
                    "message": "Updated from batch",
                },
            )
        )

        self.assertEqual(history.undo_depth(self.workspace_id), 1)
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_EDIT_NODE_PROPERTY)

    def test_path_pointer_bulk_update_roundtrips_as_one_history_entry(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        node_id = self.scene.add_node_from_type("io.path_pointer", 40.0, 60.0)
        workspace = self.model.project.workspaces[self.workspace_id]
        before = dict(workspace.nodes[node_id].properties)
        history.clear_workspace(self.workspace_id)

        self.assertTrue(
            self.scene.set_node_properties(
                node_id,
                {"path": "C:/fixtures/results", "mode": "folder"},
            )
        )

        self.assertEqual(history.undo_depth(self.workspace_id), 1)
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_EDIT_NODE_PROPERTY)
        self.assertEqual(workspace.nodes[node_id].properties["path"], "C:/fixtures/results")
        self.assertEqual(workspace.nodes[node_id].properties["mode"], "folder")

        self.assertIsNotNone(history.undo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertEqual(workspace.nodes[node_id].properties, before)

        self.assertIsNotNone(history.redo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertEqual(workspace.nodes[node_id].properties["path"], "C:/fixtures/results")
        self.assertEqual(workspace.nodes[node_id].properties["mode"], "folder")

    def test_title_only_rename_updates_node_payload_without_edge_payload_churn(self) -> None:
        source_id = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        logger_id = self.scene.add_node_from_type("core.logger", 320.0, 40.0)
        edge_id = self.scene.add_edge(source_id, "as_text", logger_id, "message")
        edge_payload_before = copy.deepcopy(self.scene.edges_model)
        nodes_changed: list[str] = []
        edges_changed: list[str] = []
        self.scene.nodes_changed.connect(lambda: nodes_changed.append("nodes"))
        self.scene.edges_changed.connect(lambda: edges_changed.append("edges"))

        self.scene.set_node_title(logger_id, "Logger Alpha")

        workspace = self.model.project.workspaces[self.workspace_id]
        node_payload = {item["node_id"]: item for item in self.scene.nodes_model}
        self.assertEqual(workspace.nodes[logger_id].title, "Logger Alpha")
        self.assertEqual(node_payload[logger_id]["title"], "Logger Alpha")
        self.assertEqual(copy.deepcopy(self.scene.edges_model), edge_payload_before)
        self.assertEqual({item["edge_id"] for item in self.scene.edges_model}, {edge_id})
        self.assertEqual(len(nodes_changed), 1)
        self.assertEqual(edges_changed, [])

    def test_compact_pill_rename_grows_left_and_undo_redo_restores_geometry(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        workspace = self.model.project.workspaces[self.workspace_id]
        long_title = "Extremely Long Compact Pill Label Used To Prove Leftward Automatic Sizing"

        for index, type_id in enumerate(
            ("data.boolean_toggle", "data.number_slider", "data.select", "core.trigger")
        ):
            with self.subTest(type_id=type_id):
                node_id = self.scene.add_node_from_type(
                    type_id,
                    300.0,
                    40.0 + index * 80.0,
                )
                original_node = workspace.nodes[node_id]
                original_payload = next(
                    item for item in self.scene.nodes_model if item["node_id"] == node_id
                )
                original_title = original_node.title
                original_x = float(original_node.x)
                original_width = float(original_payload["width"])
                original_min_width = float(
                    original_payload["surface_metrics"]["min_width"]
                )
                original_default_width = float(
                    original_payload["surface_metrics"]["default_width"]
                )
                original_extra_width = original_width - float(
                    original_payload["surface_metrics"]["min_width"]
                )
                original_right = original_x + original_width
                original_custom_width = original_node.custom_width
                history.clear_workspace(self.workspace_id)

                self.scene.set_node_title(node_id, long_title)

                renamed_node = workspace.nodes[node_id]
                renamed_payload = next(
                    item for item in self.scene.nodes_model if item["node_id"] == node_id
                )
                renamed_width = float(renamed_payload["width"])
                renamed_x = float(renamed_node.x)
                if type_id == "core.trigger":
                    pixel_size = standard_inline_property_pixel_size(
                        DEFAULT_GRAPH_LABEL_PIXEL_SIZE
                    )
                    font_weight = "demibold"
                    padding = 14.0
                    minimum_section_width = 68.0
                else:
                    pixel_size = standard_node_title_pixel_size(
                        DEFAULT_GRAPH_LABEL_PIXEL_SIZE
                    )
                    font_weight = "bold"
                    padding = 26.0
                    minimum_section_width = 82.0
                expected_title_overflow = max(
                    0.0,
                    max(
                        _estimate_standard_text_width(
                            long_title,
                            pixel_size=pixel_size,
                            font_weight=font_weight,
                        )
                        + padding,
                        minimum_section_width,
                    )
                    - max(
                        _estimate_standard_text_width(
                            original_title,
                            pixel_size=pixel_size,
                            font_weight=font_weight,
                        )
                        + padding,
                        minimum_section_width,
                    ),
                )
                self.assertEqual(history.undo_depth(self.workspace_id), 1)
                self.assertEqual(
                    history._undo_stacks[self.workspace_id][-1].action_type,
                    ACTION_RENAME_NODE,
                )
                self.assertEqual(renamed_node.title, long_title)
                self.assertGreater(renamed_width, original_width)
                self.assertLess(renamed_x, original_x)
                self.assertAlmostEqual(
                    float(renamed_payload["surface_metrics"]["min_width"])
                    - original_min_width,
                    expected_title_overflow,
                    places=6,
                )
                self.assertAlmostEqual(
                    float(renamed_payload["surface_metrics"]["default_width"])
                    - original_default_width,
                    expected_title_overflow,
                    places=6,
                )
                self.assertAlmostEqual(
                    renamed_width - float(renamed_payload["surface_metrics"]["min_width"]),
                    original_extra_width,
                    places=6,
                )
                self.assertAlmostEqual(renamed_x + renamed_width, original_right, places=6)

                self.assertIsNotNone(history.undo_workspace(self.workspace_id, workspace))
                self.scene.refresh_workspace_from_model(self.workspace_id)
                restored_node = workspace.nodes[node_id]
                restored_payload = next(
                    item for item in self.scene.nodes_model if item["node_id"] == node_id
                )
                self.assertEqual(restored_node.title, original_title)
                self.assertAlmostEqual(float(restored_node.x), original_x, places=6)
                self.assertAlmostEqual(float(restored_payload["width"]), original_width, places=6)
                self.assertEqual(restored_node.custom_width, original_custom_width)

                self.assertIsNotNone(history.redo_workspace(self.workspace_id, workspace))
                self.scene.refresh_workspace_from_model(self.workspace_id)
                redone_node = workspace.nodes[node_id]
                redone_payload = next(
                    item for item in self.scene.nodes_model if item["node_id"] == node_id
                )
                self.assertEqual(redone_node.title, long_title)
                self.assertAlmostEqual(float(redone_node.x), renamed_x, places=6)
                self.assertAlmostEqual(float(redone_payload["width"]), renamed_width, places=6)
                self.assertAlmostEqual(
                    float(redone_node.x) + float(redone_payload["width"]),
                    original_right,
                    places=6,
                )

                history.clear_workspace(self.workspace_id)
                self.scene.set_node_title(node_id, original_title)
                shortened_node = workspace.nodes[node_id]
                shortened_payload = next(
                    item for item in self.scene.nodes_model if item["node_id"] == node_id
                )
                self.assertEqual(history.undo_depth(self.workspace_id), 1)
                self.assertEqual(shortened_node.title, original_title)
                self.assertAlmostEqual(float(shortened_node.x), original_x, places=6)
                self.assertAlmostEqual(float(shortened_payload["width"]), original_width, places=6)
                self.assertAlmostEqual(
                    float(shortened_node.x) + float(shortened_payload["width"]),
                    original_right,
                    places=6,
                )
                self.assertEqual(shortened_node.custom_width, original_custom_width)

    def test_compact_pill_title_property_paths_preserve_width_and_persist(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        typography_host = _GraphLabelSizeHost()
        graph_theme_bridge = GraphThemeBridge(parent=typography_host)
        self.scene.bind_graphics_preferences_source(typography_host)
        self.scene.bind_graph_theme_bridge(graph_theme_bridge)
        workspace = self.model.project.workspaces[self.workspace_id]
        long_title = "Compact Pill Label Sized With Non Default Graph Typography"

        def payload_for(node_id: str) -> dict[str, object]:
            return next(
                item for item in self.scene.nodes_model if item["node_id"] == node_id
            )

        cases = (
            (
                "data.boolean_toggle",
                lambda node_id: self.scene.set_node_property(
                    node_id,
                    "title",
                    long_title,
                ),
                ACTION_RENAME_NODE,
            ),
            (
                "data.select",
                lambda node_id: self.scene.set_node_properties(
                    node_id,
                    {"title": long_title},
                ),
                ACTION_RENAME_NODE,
            ),
            (
                "data.number_slider",
                lambda node_id: self.scene.set_node_properties(
                    node_id,
                    {"title": long_title, "value": 7.0},
                ),
                ACTION_EDIT_NODE_PROPERTY,
            ),
        )
        renamed_ids: list[str] = []
        number_slider_before: tuple[str, float, float, float] | None = None

        for index, (type_id, rename, action_type) in enumerate(cases):
            with self.subTest(type_id=type_id):
                node_id = self.scene.add_node_from_type(
                    type_id,
                    320.0,
                    40.0 + index * 80.0,
                )
                before_node = workspace.nodes[node_id]
                before_payload = payload_for(node_id)
                before_title = before_node.title
                before_x = float(before_node.x)
                before_width = float(before_payload["width"])
                before_right = before_x + before_width
                before_min_width = float(before_payload["surface_metrics"]["min_width"])
                if type_id == "data.number_slider":
                    number_slider_before = (
                        before_title,
                        before_x,
                        before_width,
                        float(before_node.properties["value"]),
                    )
                history.clear_workspace(self.workspace_id)

                rename(node_id)

                after_node = workspace.nodes[node_id]
                after_payload = payload_for(node_id)
                after_width = float(after_payload["width"])
                expected_overflow = max(
                    _estimate_standard_text_width(
                        long_title,
                        pixel_size=standard_node_title_pixel_size(16),
                        font_weight="bold",
                    )
                    + 26.0,
                    82.0,
                ) - max(
                    _estimate_standard_text_width(
                        before_title,
                        pixel_size=standard_node_title_pixel_size(16),
                        font_weight="bold",
                    )
                    + 26.0,
                    82.0,
                )
                self.assertEqual(history.undo_depth(self.workspace_id), 1)
                self.assertEqual(
                    history._undo_stacks[self.workspace_id][-1].action_type,
                    action_type,
                )
                self.assertEqual(after_node.title, long_title)
                self.assertGreater(after_width, before_width)
                self.assertAlmostEqual(
                    float(after_node.x) + after_width,
                    before_right,
                    places=6,
                )
                self.assertAlmostEqual(
                    float(after_payload["surface_metrics"]["min_width"])
                    - before_min_width,
                    expected_overflow,
                    places=6,
                )
                renamed_ids.append(node_id)

        assert number_slider_before is not None
        number_slider_id = renamed_ids[-1]
        self.assertIsNotNone(history.undo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        restored_number = workspace.nodes[number_slider_id]
        restored_payload = payload_for(number_slider_id)
        self.assertEqual(restored_number.title, number_slider_before[0])
        self.assertAlmostEqual(float(restored_number.x), number_slider_before[1], places=6)
        self.assertAlmostEqual(float(restored_payload["width"]), number_slider_before[2], places=6)
        self.assertAlmostEqual(
            float(restored_number.properties["value"]),
            number_slider_before[3],
            places=6,
        )
        self.assertIsNotNone(history.redo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)

        trigger_id = self.scene.add_node_from_type("core.trigger", 320.0, 300.0)
        trigger_payload = payload_for(trigger_id)
        self.scene.resize_node(
            trigger_id,
            float(trigger_payload["width"]) + 40.0,
            float(trigger_payload["height"]),
        )
        trigger_before = workspace.nodes[trigger_id]
        trigger_payload = payload_for(trigger_id)
        trigger_right = float(trigger_before.x) + float(trigger_payload["width"])
        trigger_extra_width = float(trigger_payload["width"]) - float(
            trigger_payload["surface_metrics"]["min_width"]
        )
        history.clear_workspace(self.workspace_id)

        self.scene.set_node_title(trigger_id, long_title)

        trigger_after = workspace.nodes[trigger_id]
        trigger_payload = payload_for(trigger_id)
        self.assertEqual(history.undo_depth(self.workspace_id), 1)
        self.assertEqual(
            history._undo_stacks[self.workspace_id][-1].action_type,
            ACTION_RENAME_NODE,
        )
        self.assertAlmostEqual(
            float(trigger_payload["width"])
            - float(trigger_payload["surface_metrics"]["min_width"]),
            trigger_extra_width,
            places=6,
        )
        self.assertAlmostEqual(
            float(trigger_after.x) + float(trigger_payload["width"]),
            trigger_right,
            places=6,
        )

        serializer = JsonProjectSerializer(self.registry)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "compact-pill-autosize.cxproj"
            serializer.save(str(path), self.model.project)
            loaded = serializer.load(str(path))
        loaded_workspace = loaded.workspaces[self.workspace_id]
        for node_id in (*renamed_ids, trigger_id):
            with self.subTest(persisted_node_id=node_id):
                source = workspace.nodes[node_id]
                restored = loaded_workspace.nodes[node_id]
                self.assertEqual(restored.title, source.title)
                self.assertAlmostEqual(float(restored.x), float(source.x), places=6)
                self.assertEqual(restored.custom_width, source.custom_width)
                self.assertEqual(restored.properties, source.properties)

    def test_shortening_title_refreshes_standard_node_min_width_payload(self) -> None:
        node_id = self.scene.add_node_from_type("core.logger", 40.0, 60.0)
        workspace = self.model.project.workspaces[self.workspace_id]
        baseline_payload = {item["node_id"]: item for item in self.scene.nodes_model}[node_id]
        baseline_min_width = float(baseline_payload["surface_metrics"]["min_width"])
        long_title = "Superconducting Cryogenic Feed Line Pressure Telemetry Resolver"

        self.scene.set_node_title(node_id, long_title)
        long_payload = {item["node_id"]: item for item in self.scene.nodes_model}[node_id]
        long_min_width = float(long_payload["surface_metrics"]["min_width"])
        long_title_width = float(long_payload["surface_metrics"]["standard_title_full_width"])

        self.assertGreater(long_min_width, baseline_min_width)
        self.assertGreater(long_title_width, baseline_min_width)

        self.scene.resize_node(node_id, long_min_width, float(long_payload["height"]))
        resized_payload = {item["node_id"]: item for item in self.scene.nodes_model}[node_id]
        self.assertAlmostEqual(float(workspace.nodes[node_id].custom_width or 0.0), long_min_width, places=6)
        self.assertAlmostEqual(float(resized_payload["width"]), long_min_width, places=6)

        self.scene.set_node_title(node_id, "Log")
        shortened_payload = {item["node_id"]: item for item in self.scene.nodes_model}[node_id]
        shortened_minimap_payload = {
            item["node_id"]: item for item in self.scene.minimap_nodes_model
        }[node_id]
        shortened_min_width = float(shortened_payload["surface_metrics"]["min_width"])
        shortened_title_width = float(shortened_payload["surface_metrics"]["standard_title_full_width"])

        self.assertLess(shortened_min_width, long_min_width)
        self.assertLess(shortened_title_width, long_title_width)
        fitted_width = float(shortened_payload["surface_metrics"]["default_width"])
        self.assertLess(fitted_width, long_min_width)
        self.assertAlmostEqual(float(shortened_payload["width"]), fitted_width, places=6)
        self.assertAlmostEqual(float(shortened_minimap_payload["width"]), fitted_width, places=6)

        self.scene.resize_node(node_id, shortened_min_width, float(shortened_payload["height"]))
        final_payload = {item["node_id"]: item for item in self.scene.nodes_model}[node_id]
        final_minimap_payload = {item["node_id"]: item for item in self.scene.minimap_nodes_model}[node_id]
        self.assertLess(float(final_payload["width"]), long_min_width)
        self.assertAlmostEqual(float(final_payload["width"]), fitted_width, places=6)
        self.assertAlmostEqual(float(final_minimap_payload["width"]), fitted_width, places=6)

    def test_rename_undo_redo_refreshes_node_payload_without_edge_payload_churn(self) -> None:
        source_id = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        logger_id = self.scene.add_node_from_type("core.logger", 320.0, 40.0)
        self.scene.add_edge(source_id, "as_text", logger_id, "message")
        workspace = self.model.project.workspaces[self.workspace_id]
        original_title = workspace.nodes[logger_id].title
        edge_payload_before = copy.deepcopy(self.scene.edges_model)
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        history.clear_workspace(self.workspace_id)
        nodes_changed: list[str] = []
        edges_changed: list[str] = []
        self.scene.nodes_changed.connect(lambda: nodes_changed.append("nodes"))
        self.scene.edges_changed.connect(lambda: edges_changed.append("edges"))

        self.scene.set_node_title(logger_id, "Logger Alpha")
        rebuild_calls: list[str] = []
        original_rebuild_models = self.scene._scene_context.rebuild_models

        def _unexpected_rebuild_models() -> None:
            rebuild_calls.append("rebuild")
            original_rebuild_models()

        self.scene._scene_context.rebuild_models = _unexpected_rebuild_models
        try:
            undo_entry = history.undo_workspace(self.workspace_id, workspace)
            self.assertIsNotNone(undo_entry)
            self.assertEqual(undo_entry.action_type, ACTION_RENAME_NODE)
            self.scene.refresh_workspace_from_model(self.workspace_id)
        finally:
            self.scene._scene_context.rebuild_models = original_rebuild_models

        node_payload = {item["node_id"]: item for item in self.scene.nodes_model}
        self.assertEqual(workspace.nodes[logger_id].title, original_title)
        self.assertEqual(node_payload[logger_id]["title"], original_title)
        self.assertEqual(copy.deepcopy(self.scene.edges_model), edge_payload_before)
        self.assertEqual(len(nodes_changed), 2)
        self.assertEqual(edges_changed, [])

        original_rebuild_models = self.scene._scene_context.rebuild_models
        self.scene._scene_context.rebuild_models = _unexpected_rebuild_models
        try:
            redo_entry = history.redo_workspace(self.workspace_id, workspace)
            self.assertIsNotNone(redo_entry)
            self.assertEqual(redo_entry.action_type, ACTION_RENAME_NODE)
            self.scene.refresh_workspace_from_model(self.workspace_id)
        finally:
            self.scene._scene_context.rebuild_models = original_rebuild_models

        self.assertEqual(rebuild_calls, [])
        node_payload = {item["node_id"]: item for item in self.scene.nodes_model}
        self.assertEqual(workspace.nodes[logger_id].title, "Logger Alpha")
        self.assertEqual(node_payload[logger_id]["title"], "Logger Alpha")
        self.assertEqual(copy.deepcopy(self.scene.edges_model), edge_payload_before)
        self.assertEqual(len(nodes_changed), 3)
        self.assertEqual(edges_changed, [])

    def test_persistent_node_elapsed_action_types_split_property_and_cosmetic_mutations(self) -> None:
        source_id = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        logger_id = self.scene.add_node_from_type("core.logger", 320.0, 40.0)
        edge_target_id = self.scene.add_node_from_type("core.python_script", 640.0, 40.0)
        passive_id = self.scene.add_node_from_type("passive.flowchart.process", 960.0, 40.0)
        edge_id = self.scene.add_edge(source_id, "value", edge_target_id, "payload")
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        history.clear_workspace(self.workspace_id)

        self.scene.set_node_property(logger_id, "message", "Updated from single property")
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_EDIT_NODE_PROPERTY)
        history.clear_workspace(self.workspace_id)

        self.scene.set_node_title(logger_id, "Logger Alpha")
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_RENAME_NODE)
        history.clear_workspace(self.workspace_id)

        self.assertTrue(self.scene.set_node_properties(logger_id, {"title": "Logger Beta"}))
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_RENAME_NODE)
        history.clear_workspace(self.workspace_id)

        self.assertTrue(
            self.scene.set_node_properties(
                logger_id,
                {
                    "title": "Logger Gamma",
                    "message": "Updated from batch",
                },
            )
        )
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_EDIT_NODE_PROPERTY)
        history.clear_workspace(self.workspace_id)

        self.scene.set_node_visual_style(passive_id, {"fill": "#102030", "badge": {"shape": "pill"}})
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_EDIT_NODE_STYLE)
        history.clear_workspace(self.workspace_id)

        self.scene.set_edge_label(edge_id, "Primary path")
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_EDIT_EDGE_LABEL)
        history.clear_workspace(self.workspace_id)

        self.scene.set_edge_visual_style(edge_id, {"stroke": "dashed", "arrow": {"kind": "none"}})
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_EDIT_EDGE_STYLE)
        history.clear_workspace(self.workspace_id)

        self.scene.set_node_port_label(logger_id, "message", "Message Input")
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_EDIT_PORT_LABEL)

    def test_late_single_property_update_for_deleted_node_is_ignored(self) -> None:
        logger_id = self.scene.add_node_from_type("core.logger", 320.0, 40.0)
        self.scene.remove_node(logger_id)

        self.scene.set_node_property(logger_id, "message", "Late browser-state style update")

        self.assertNotIn(logger_id, self.model.active_workspace.nodes)

    def test_persistent_node_elapsed_action_types_keep_structural_and_layout_labels_distinct(self) -> None:
        source_id = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        target_id = self.scene.add_node_from_type("core.python_script", 320.0, 60.0)
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        history.clear_workspace(self.workspace_id)

        added_id = self.scene.add_node_from_type("core.python_script", 640.0, 80.0)
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_ADD_NODE)
        history.clear_workspace(self.workspace_id)

        edge_id = self.scene.add_edge(source_id, "value", added_id, "payload")
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_ADD_EDGE)
        history.clear_workspace(self.workspace_id)

        self.scene.move_node(source_id, 80.0, 20.0)
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_MOVE_NODE)
        history.clear_workspace(self.workspace_id)

        self.scene.resize_node(target_id, 420.0, 180.0)
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_RESIZE_NODE)
        history.clear_workspace(self.workspace_id)

        self.scene.set_node_collapsed(target_id, True)
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_TOGGLE_COLLAPSED)
        history.clear_workspace(self.workspace_id)

        self.scene.add_edge(source_id, "as_text", target_id, "payload")
        history.clear_workspace(self.workspace_id)

        self.scene.set_exposed_port(source_id, "as_text", False)
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_TOGGLE_EXPOSED_PORT)
        history.clear_workspace(self.workspace_id)

        self.scene.remove_edge(edge_id)
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_REMOVE_EDGE)
        history.clear_workspace(self.workspace_id)

        self.scene.remove_node(added_id)
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_REMOVE_NODE)

    def test_persistent_node_elapsed_action_types_split_duplicate_group_and_comment_flows(self) -> None:
        source_id = self.scene.add_node_from_type("core.constant", 20.0, 40.0)
        grouped_if_id = self.scene.add_node_from_type("core.if", 320.0, 60.0)
        grouped_constant_id = self.scene.add_node_from_type("core.constant", 220.0, 190.0)
        target_id = self.scene.add_node_from_type("core.python_script", 640.0, 90.0)
        external_script_id = self.scene.add_node_from_type("core.python_script", 700.0, 230.0)

        self.scene.add_edge(source_id, "value", grouped_if_id, "condition")
        self.scene.add_edge(grouped_constant_id, "as_text", grouped_if_id, "true_value")
        self.scene.add_edge(grouped_if_id, "result", target_id, "payload")
        self.scene.add_edge(grouped_constant_id, "value", external_script_id, "payload")

        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)

        self.scene.select_node(grouped_if_id, False)
        self.scene.select_node(grouped_constant_id, True)
        history.clear_workspace(self.workspace_id)

        self.assertTrue(self.scene.duplicate_selected_subgraph())
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_DUPLICATE_SUBGRAPH)
        history.clear_workspace(self.workspace_id)

        self.scene.select_node(grouped_if_id, False)
        self.scene.select_node(grouped_constant_id, True)
        fragment = self.scene.serialize_selected_subgraph_fragment()
        self.assertIsNotNone(fragment)
        assert fragment is not None
        self.assertTrue(self.scene.paste_subgraph_fragment(fragment, 960.0, 240.0))
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_PASTE_SUBGRAPH)
        history.clear_workspace(self.workspace_id)

        self.scene.select_node(grouped_if_id, False)
        self.scene.select_node(grouped_constant_id, True)
        self.assertTrue(self.scene.group_selected_nodes())
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_GROUP_SELECTED_NODES)

        shell_id = self.scene.selected_node_id()
        self.assertIsNotNone(shell_id)
        assert shell_id is not None
        history.clear_workspace(self.workspace_id)

        self.scene.select_node(shell_id, False)
        self.assertTrue(self.scene.ungroup_selected_subnode())
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_UNGROUP_SELECTED_SUBNODE)
        history.clear_workspace(self.workspace_id)

        self.scene.select_node(grouped_if_id, False)
        self.scene.select_node(grouped_constant_id, True)
        self.assertTrue(self.scene.wrap_selected_nodes_in_group_backdrop())
        self.assertEqual(history._undo_stacks[self.workspace_id][-1].action_type, ACTION_WRAP_GROUP)

    def test_hiding_connected_port_removes_edges_immediately(self) -> None:
        source_id = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        target_id = self.scene.add_node_from_type("core.python_script", 320.0, 30.0)
        edge_id = self.scene.add_edge(source_id, "as_text", target_id, "payload")

        self.scene.set_exposed_port(source_id, "as_text", False)

        workspace = self.model.project.workspaces[self.workspace_id]
        self.assertNotIn(edge_id, workspace.edges)
        self.assertIsNone(self.scene.edge_item(edge_id))

    def test_graph_theme_bridge_rebuilds_scene_payload_semantics(self) -> None:
        graph_theme_bridge = GraphThemeBridge(theme_id="graph_stitch_dark")
        self.scene.bind_graph_theme_bridge(graph_theme_bridge)
        nodes_changed: list[str] = []
        edges_changed: list[str] = []
        self.scene.nodes_changed.connect(lambda: nodes_changed.append("nodes"))
        self.scene.edges_changed.connect(lambda: edges_changed.append("edges"))

        start_id = self.scene.add_node_from_type("core.python_script", 0.0, 0.0)
        constant_id = self.scene.add_node_from_type("core.constant", 220.0, 0.0)
        branch_id = self.scene.add_node_from_type("core.if", 480.0, 0.0)
        invalid_edge = self.model._add_edge_record(
            self.workspace_id,
            source_node_id=constant_id,
            source_port_key="as_text",
            target_node_id=branch_id,
            target_port_key="condition",
        )
        edge_id = invalid_edge.edge_id
        self.scene.refresh_workspace_from_model(self.workspace_id)

        node_payload = {item["node_id"]: item for item in self.scene.nodes_model}
        edge_payload = {item["edge_id"]: item for item in self.scene.edges_model}
        self.assertNotIn("accent", node_payload[start_id])
        self.assertTrue(edge_payload[edge_id]["data_type_warning"])
        self.assertEqual(edge_payload[edge_id]["color"], GRAPH_STITCH_DARK_EDGE_TOKENS_V1.warning_stroke)

        nodes_count_before = len(nodes_changed)
        edges_count_before = len(edges_changed)
        graph_theme_bridge.apply_theme("graph_stitch_light")

        self.assertGreater(len(nodes_changed), nodes_count_before)
        self.assertGreater(len(edges_changed), edges_count_before)
        edge_payload = {item["edge_id"]: item for item in self.scene.edges_model}
        self.assertEqual(edge_payload[edge_id]["color"], GRAPH_STITCH_LIGHT_EDGE_TOKENS_V1.warning_stroke)

    def test_graph_theme_bridge_accepts_custom_theme_payloads_and_rebuilds_scene(self) -> None:
        custom_theme = copy.deepcopy(resolve_graph_theme("graph_stitch_dark").as_dict())
        custom_theme["theme_id"] = "custom_graph_theme_deadbeef"
        custom_theme["label"] = "Ocean Wire"
        custom_theme["category_accent_tokens"] = {"core": "#44AAFF"}
        custom_theme["edge_tokens"]["warning_stroke"] = "#11AA66"

        graph_theme_bridge = GraphThemeBridge(theme_id=custom_theme)
        self.scene.bind_graph_theme_bridge(graph_theme_bridge)
        nodes_changed: list[str] = []
        edges_changed: list[str] = []
        self.scene.nodes_changed.connect(lambda: nodes_changed.append("nodes"))
        self.scene.edges_changed.connect(lambda: edges_changed.append("edges"))

        start_id = self.scene.add_node_from_type("core.python_script", 0.0, 0.0)
        constant_id = self.scene.add_node_from_type("core.constant", 220.0, 0.0)
        branch_id = self.scene.add_node_from_type("core.if", 480.0, 0.0)
        invalid_edge = self.model._add_edge_record(
            self.workspace_id,
            source_node_id=constant_id,
            source_port_key="as_text",
            target_node_id=branch_id,
            target_port_key="condition",
        )
        edge_id = invalid_edge.edge_id
        self.scene.refresh_workspace_from_model(self.workspace_id)

        node_payload = {item["node_id"]: item for item in self.scene.nodes_model}
        edge_payload = {item["edge_id"]: item for item in self.scene.edges_model}
        self.assertNotIn("accent", node_payload[start_id])
        self.assertEqual(edge_payload[edge_id]["color"], "#11AA66")

        custom_theme["category_accent_tokens"]["core"] = "#C955CC"
        custom_theme["edge_tokens"]["warning_stroke"] = "#1188CC"
        nodes_count_before = len(nodes_changed)
        edges_count_before = len(edges_changed)
        graph_theme_bridge.apply_theme(custom_theme)

        self.assertGreater(len(nodes_changed), nodes_count_before)
        self.assertGreater(len(edges_changed), edges_count_before)
        node_payload = {item["node_id"]: item for item in self.scene.nodes_model}
        edge_payload = {item["edge_id"]: item for item in self.scene.edges_model}
        self.assertNotIn("accent", node_payload[start_id])
        self.assertEqual(edge_payload[edge_id]["color"], "#1188CC")

    def test_connect_nodes_uses_only_currently_exposed_ports(self) -> None:
        source_id = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        target_id = self.scene.add_node_from_type("core.logger", 320.0, 30.0)
        self.scene.set_exposed_port(source_id, "value", False)
        self.scene.set_exposed_port(source_id, "as_text", False)

        with self.assertRaises(ValueError):
            self.scene.connect_nodes(source_id, target_id)

    def test_add_edge_rejects_flow_to_data_kind_mismatch(self) -> None:
        source_id = self.scene.add_node_from_type("passive.flowchart.start", 0.0, 0.0)
        target_id = self.scene.add_node_from_type("core.logger", 320.0, 30.0)

        self.assertTrue(self.scene.are_data_types_compatible("flow", "flow"))
        with self.assertRaises(ValueError):
            self.scene.add_edge(source_id, "right", target_id, "message")

    def test_add_edge_replaces_existing_incoming_connection_for_data_input(self) -> None:
        first_source_id = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        second_source_id = self.scene.add_node_from_type("core.constant", 0.0, 120.0)
        target_id = self.scene.add_node_from_type("core.python_script", 320.0, 30.0)

        first_edge_id = self.scene.add_edge(first_source_id, "value", target_id, "payload")
        replacement_edge_id = self.scene.add_edge(second_source_id, "value", target_id, "payload")

        workspace = self.model.project.workspaces[self.workspace_id]
        self.assertNotIn(first_edge_id, workspace.edges)
        self.assertIn(replacement_edge_id, workspace.edges)
        self.assertEqual(len(workspace.edges), 1)

    def test_pin_kind_change_prunes_invalid_shell_edge_immediately(self) -> None:
        source_id = self.scene.add_node_from_type("core.constant", 0.0, 0.0)
        shell_id = self.scene.add_node_from_type("core.subnode", 240.0, 30.0)
        pin_in = self.scene.add_subnode_shell_pin(shell_id, "core.subnode_input")

        edge_id = self.scene.add_edge(source_id, "value", shell_id, pin_in)

        workspace = self.model.project.workspaces[self.workspace_id]
        self.assertIn(edge_id, workspace.edges)

        self.scene.set_node_property(pin_in, "kind", "flow")

        self.assertNotIn(edge_id, workspace.edges)
        self.assertEqual(self.scene.edges_model, [])

    def test_subnode_shell_ports_follow_direct_pin_sort_and_pin_properties(self) -> None:
        shell_id = self.scene.add_node_from_type("core.subnode", 200.0, 120.0)
        pin_in_flow = self.scene.add_node_from_type("core.subnode_input", 30.0, 10.0)
        pin_in_data = self.scene.add_node_from_type("core.subnode_input", 30.0, 10.0)
        pin_out_data = self.scene.add_node_from_type("core.subnode_output", 90.0, 10.0)
        pin_out_flow = self.scene.add_node_from_type("core.subnode_output", 20.0, 50.0)
        non_pin_child = self.scene.add_node_from_type("core.logger", 60.0, 15.0)
        nested_pin = self.scene.add_node_from_type("core.subnode_input", 15.0, 5.0)

        workspace = self.model.project.workspaces[self.workspace_id]
        workspace.nodes[pin_in_flow].parent_node_id = shell_id
        workspace.nodes[pin_in_data].parent_node_id = shell_id
        workspace.nodes[pin_out_data].parent_node_id = shell_id
        workspace.nodes[pin_out_flow].parent_node_id = shell_id
        workspace.nodes[non_pin_child].parent_node_id = shell_id
        workspace.nodes[nested_pin].parent_node_id = non_pin_child

        self.scene.set_node_property(pin_in_flow, "label", "Flow In")
        self.scene.set_node_property(pin_in_flow, "kind", "flow")
        self.scene.set_node_property(
            pin_in_flow,
            "data_type",
            STRING_DATA_TYPE_ID,
        )
        self.scene.set_node_property(pin_in_data, "label", "Flag In")
        self.scene.set_node_property(pin_in_data, "kind", "data")
        self.scene.set_node_property(
            pin_in_data,
            "data_type",
            BOOLEAN_DATA_TYPE_ID,
        )
        self.scene.set_node_property(pin_out_data, "label", "Result Out")
        self.scene.set_node_property(pin_out_data, "kind", "data")
        self.scene.set_node_property(
            pin_out_data,
            "data_type",
            DOUBLE_DATA_TYPE_ID,
        )
        self.scene.set_node_property(pin_out_flow, "label", "Flow Out")
        self.scene.set_node_property(pin_out_flow, "kind", "flow")
        self.scene.set_node_property(
            pin_out_flow,
            "data_type",
            STRING_DATA_TYPE_ID,
        )
        self.scene.refresh_workspace_from_model(self.workspace_id)

        root_payload = {item["node_id"]: item for item in self.scene.nodes_model}
        shell_ports = root_payload[shell_id]["ports"]
        direct_pins = [pin_in_flow, pin_in_data, pin_out_data, pin_out_flow]
        expected_order = sorted(
            direct_pins,
            key=lambda node_id: (
                float(workspace.nodes[node_id].y),
                float(workspace.nodes[node_id].x),
                node_id,
            ),
        )
        self.assertEqual([port["key"] for port in shell_ports], expected_order)
        self.assertEqual(len(shell_ports), 4)

        shell_port_by_key = {port["key"]: port for port in shell_ports}
        self.assertEqual(shell_port_by_key[pin_in_flow]["label"], "Flow In")
        self.assertEqual(shell_port_by_key[pin_in_flow]["direction"], "in")
        self.assertEqual(shell_port_by_key[pin_in_flow]["kind"], "flow")
        self.assertEqual(
            shell_port_by_key[pin_in_flow]["data_type"],
            GRAPH_DATA_TYPE_ID,
        )
        self.assertEqual(shell_port_by_key[pin_in_data]["label"], "Flag In")
        self.assertEqual(shell_port_by_key[pin_in_data]["direction"], "in")
        self.assertEqual(
            shell_port_by_key[pin_in_data]["data_type"],
            BOOLEAN_DATA_TYPE_ID,
        )
        self.assertEqual(shell_port_by_key[pin_out_data]["label"], "Result Out")
        self.assertEqual(shell_port_by_key[pin_out_data]["direction"], "out")
        self.assertEqual(
            shell_port_by_key[pin_out_data]["data_type"],
            DOUBLE_DATA_TYPE_ID,
        )
        self.assertEqual(shell_port_by_key[pin_out_flow]["label"], "Flow Out")
        self.assertEqual(shell_port_by_key[pin_out_flow]["direction"], "out")
        self.assertEqual(shell_port_by_key[pin_out_flow]["kind"], "flow")
        self.assertEqual(
            shell_port_by_key[pin_out_flow]["data_type"],
            GRAPH_DATA_TYPE_ID,
        )

        self.assertNotIn(pin_in_flow, root_payload)
        self.assertTrue(self.scene.open_subnode_scope(shell_id))

        nested_payload = {item["node_id"]: item for item in self.scene.nodes_model}
        self.assertIn(pin_in_flow, nested_payload)
        pin_payload = nested_payload[pin_in_flow]["ports"]
        self.assertEqual(len(pin_payload), 1)
        self.assertEqual(pin_payload[0]["key"], "pin")
        self.assertEqual(pin_payload[0]["label"], "Flow In")
        self.assertEqual(pin_payload[0]["kind"], "flow")
        self.assertEqual(pin_payload[0]["data_type"], GRAPH_DATA_TYPE_ID)

    def test_add_subnode_shell_pin_uses_unique_labels_and_exposes_shell_ports(self) -> None:
        shell_id = self.scene.add_node_from_type("core.subnode", 200.0, 120.0)
        first_input_id = self.scene.add_subnode_shell_pin(shell_id, "core.subnode_input")
        second_input_id = self.scene.add_subnode_shell_pin(shell_id, "core.subnode_input")
        output_id = self.scene.add_subnode_shell_pin(shell_id, "core.subnode_output")

        workspace = self.model.project.workspaces[self.workspace_id]
        shell_node = workspace.nodes[shell_id]
        self.assertTrue(first_input_id)
        self.assertTrue(second_input_id)
        self.assertTrue(output_id)
        self.assertEqual(workspace.nodes[first_input_id].parent_node_id, shell_id)
        self.assertEqual(workspace.nodes[second_input_id].parent_node_id, shell_id)
        self.assertEqual(workspace.nodes[output_id].parent_node_id, shell_id)
        self.assertEqual(workspace.nodes[first_input_id].properties["label"], "Input")
        self.assertEqual(workspace.nodes[second_input_id].properties["label"], "Input 2")
        self.assertEqual(workspace.nodes[output_id].properties["label"], "Output")
        self.assertTrue(bool(shell_node.exposed_ports[first_input_id]))
        self.assertTrue(bool(shell_node.exposed_ports[second_input_id]))
        self.assertTrue(bool(shell_node.exposed_ports[output_id]))
        self.assertLess(float(workspace.nodes[first_input_id].x), float(workspace.nodes[output_id].x))
        self.assertLess(float(workspace.nodes[first_input_id].y), float(workspace.nodes[second_input_id].y))

        shell_payload = next(item for item in self.scene.nodes_model if item["node_id"] == shell_id)
        shell_ports = {port["key"]: port for port in shell_payload["ports"]}
        self.assertEqual(shell_ports[first_input_id]["label"], "Input")
        self.assertEqual(shell_ports[second_input_id]["label"], "Input 2")
        self.assertEqual(shell_ports[output_id]["label"], "Output")

    def test_scope_navigation_filters_nodes_edges_and_assigns_new_nodes_to_active_scope(self) -> None:
        shell_id = self.scene.add_node_from_type("core.subnode", 200.0, 120.0)
        root_source_id = self.scene.add_node_from_type("core.constant", 20.0, 30.0)
        root_target_id = self.scene.add_node_from_type("core.python_script", 520.0, 30.0)
        pin_in = self.scene.add_node_from_type("core.subnode_input", 30.0, 30.0)
        pin_out = self.scene.add_node_from_type("core.subnode_output", 90.0, 30.0)
        nested_logger = self.scene.add_node_from_type("core.logger", 160.0, 120.0)
        workspace = self.model.project.workspaces[self.workspace_id]
        workspace.nodes[pin_in].parent_node_id = shell_id
        workspace.nodes[pin_out].parent_node_id = shell_id
        workspace.nodes[nested_logger].parent_node_id = shell_id
        self.scene.refresh_workspace_from_model(self.workspace_id)

        # Root scope only shows direct workspace children.
        root_node_ids = {item["node_id"] for item in self.scene.nodes_model}
        self.assertEqual(root_node_ids, {shell_id, root_source_id, root_target_id})
        self.assertEqual(self.scene.active_scope_path, [])
        self.assertEqual([item["node_id"] for item in self.scene.scope_breadcrumb_model], [""])

        self.scene.add_edge(root_source_id, "value", root_target_id, "payload")
        self.scene.add_edge(root_source_id, "as_text", shell_id, pin_in)
        self.assertEqual({item["edge_id"] for item in self.scene.edges_model}, set(workspace.edges))

        self.assertTrue(self.scene.open_subnode_scope(shell_id))
        self.assertEqual(self.scene.active_scope_path, [shell_id])
        breadcrumb_ids = [item["node_id"] for item in self.scene.scope_breadcrumb_model]
        self.assertEqual(breadcrumb_ids, ["", shell_id])

        nested_node_ids = {item["node_id"] for item in self.scene.nodes_model}
        self.assertEqual(nested_node_ids, {pin_in, pin_out, nested_logger})
        self.assertEqual(self.scene.edges_model, [])

        created_inside_scope = self.scene.add_node_from_type("core.constant", 300.0, 150.0)
        self.assertEqual(workspace.nodes[created_inside_scope].parent_node_id, shell_id)

        self.assertTrue(self.scene.navigate_scope_parent())
        self.assertEqual(self.scene.active_scope_path, [])
        self.assertFalse(self.scene.navigate_scope_parent())
        self.assertFalse(self.scene.navigate_scope_root())

    def test_active_subnode_scope_add_node_roundtrips_history(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        shell_id = self.scene.add_node_from_type("core.subnode", 200.0, 120.0)
        workspace = self.model.project.workspaces[self.workspace_id]

        self.assertTrue(self.scene.open_subnode_scope(shell_id))
        self.assertEqual(self.scene.active_scope_path, [shell_id])
        history.clear_workspace(self.workspace_id)

        child_id = self.scene.add_node_from_type("core.logger", 300.0, 150.0)

        self.assertEqual(history.undo_depth(self.workspace_id), 1)
        self.assertEqual(history.redo_depth(self.workspace_id), 0)
        self.assertEqual(workspace.nodes[child_id].parent_node_id, shell_id)
        self.assertIn(child_id, {item["node_id"] for item in self.scene.nodes_model})

        self.assertIsNotNone(history.undo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertEqual(history.undo_depth(self.workspace_id), 0)
        self.assertEqual(history.redo_depth(self.workspace_id), 1)
        self.assertEqual(self.scene.active_scope_path, [shell_id])
        self.assertNotIn(child_id, workspace.nodes)
        self.assertNotIn(child_id, {item["node_id"] for item in self.scene.nodes_model})

        self.assertIsNotNone(history.redo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertEqual(history.undo_depth(self.workspace_id), 1)
        self.assertEqual(history.redo_depth(self.workspace_id), 0)
        self.assertEqual(self.scene.active_scope_path, [shell_id])
        self.assertEqual(workspace.nodes[child_id].parent_node_id, shell_id)
        self.assertIn(child_id, {item["node_id"] for item in self.scene.nodes_model})

    def test_node_comments_project_for_nodes_inside_active_subnode_scope(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        shell_id = self.scene.add_node_from_type("core.subnode", 200.0, 120.0)
        workspace = self.model.project.workspaces[self.workspace_id]
        self.assertTrue(self.scene.open_subnode_scope(shell_id))
        child_id = self.scene.add_node_from_type("core.logger", 300.0, 150.0)
        history.clear_workspace(self.workspace_id)

        stored_id = self.scene.upsert_node_comment(
            child_id,
            "",
            "Scoped node review note.",
            "",
            "",
            False,
            True,
            False,
        )

        self.assertTrue(stored_id.startswith("comment"))
        self.assertEqual(history.undo_depth(self.workspace_id), 1)
        self.assertEqual(workspace.nodes[child_id].parent_node_id, shell_id)
        self.assertEqual(len(workspace.nodes[child_id].comments), 1)
        scoped_payload = next(item for item in self.scene.nodes_model if item["node_id"] == child_id)
        self.assertEqual(scoped_payload["comment_count"], 1)
        self.assertEqual(scoped_payload["comment_badge"]["count"], 1)
        self.assertEqual(scoped_payload["comment_badge"]["open_count"], 1)
        self.assertEqual(
            getattr(self.scene.state_bridge, "node_delta_payload", {})["reason"],
            "node_comment_payload",
        )

        self.assertTrue(self.scene.navigate_scope_root())
        self.assertNotIn(child_id, {item["node_id"] for item in self.scene.nodes_model})
        self.assertEqual(len(workspace.nodes[child_id].comments), 1)

        self.assertTrue(self.scene.open_subnode_scope(shell_id))
        scoped_payload = next(item for item in self.scene.nodes_model if item["node_id"] == child_id)
        self.assertEqual(scoped_payload["comments"][0]["body"], "Scoped node review note.")

    def test_connect_nodes_uses_dynamic_subnode_default_ports(self) -> None:
        source_id = self.scene.add_node_from_type("core.constant", 20.0, 30.0)
        shell_id = self.scene.add_node_from_type("core.subnode", 260.0, 30.0)
        target_id = self.scene.add_node_from_type("core.python_script", 520.0, 30.0)
        pin_in = self.scene.add_node_from_type("core.subnode_input", 40.0, 40.0)
        pin_out = self.scene.add_node_from_type("core.subnode_output", 80.0, 40.0)

        workspace = self.model.project.workspaces[self.workspace_id]
        workspace.nodes[pin_in].parent_node_id = shell_id
        workspace.nodes[pin_out].parent_node_id = shell_id
        self.scene.refresh_workspace_from_model(self.workspace_id)

        edge_into_shell_id = self.scene.connect_nodes(source_id, shell_id)
        edge_out_of_shell_id = self.scene.connect_nodes(shell_id, target_id)

        edge_into_shell = workspace.edges[edge_into_shell_id]
        edge_out_of_shell = workspace.edges[edge_out_of_shell_id]
        self.assertEqual(edge_into_shell.source_node_id, source_id)
        self.assertEqual(edge_into_shell.source_port_key, "value")
        self.assertEqual(edge_into_shell.target_node_id, shell_id)
        self.assertEqual(edge_into_shell.target_port_key, pin_in)
        self.assertEqual(edge_out_of_shell.source_node_id, shell_id)
        self.assertEqual(edge_out_of_shell.source_port_key, pin_out)
        self.assertEqual(edge_out_of_shell.target_node_id, target_id)
        self.assertEqual(edge_out_of_shell.target_port_key, "payload")

    def test_workspace_and_selection_bounds_helpers(self) -> None:
        node_a = self.scene.add_node_from_type("core.constant", 10.0, 20.0)
        node_b = self.scene.add_node_from_type("core.python_script", 340.0, 160.0)

        workspace_bounds = self.scene.workspace_scene_bounds()
        self.assertIsNotNone(workspace_bounds)
        node_a_bounds = self.scene.node_bounds(node_a)
        node_b_bounds = self.scene.node_bounds(node_b)
        self.assertIsNotNone(node_a_bounds)
        self.assertIsNotNone(node_b_bounds)
        expected_workspace_bounds = node_a_bounds.united(node_b_bounds)
        self.assertAlmostEqual(workspace_bounds.x(), expected_workspace_bounds.x(), places=6)
        self.assertAlmostEqual(workspace_bounds.y(), expected_workspace_bounds.y(), places=6)
        self.assertAlmostEqual(workspace_bounds.width(), expected_workspace_bounds.width(), places=6)
        self.assertAlmostEqual(workspace_bounds.height(), expected_workspace_bounds.height(), places=6)

        self.scene.select_node(node_b)
        selection_bounds = self.scene.selection_bounds()
        self.assertIsNotNone(selection_bounds)
        self.assertAlmostEqual(selection_bounds.x(), node_b_bounds.x(), places=6)
        self.assertAlmostEqual(selection_bounds.y(), node_b_bounds.y(), places=6)
        self.assertAlmostEqual(selection_bounds.width(), node_b_bounds.width(), places=6)
        self.assertAlmostEqual(selection_bounds.height(), node_b_bounds.height(), places=6)

        self.scene.clear_selection()
        self.assertIsNone(self.scene.selection_bounds())

    def test_selection_bounds_include_expanded_settings_group_height(self) -> None:
        node_id = self.scene.add_node_from_type(
            "tests.track_b_settings_groups",
            40.0,
            60.0,
        )
        collapsed_payload = next(
            item for item in self.scene.nodes_model if item["node_id"] == node_id
        )

        self.assertTrue(
            self.scene.set_node_settings_group_expanded(node_id, "general", True)
        )
        expanded_payload = next(
            item for item in self.scene.nodes_model if item["node_id"] == node_id
        )
        self.scene.select_node(node_id)
        node_bounds = self.scene.node_bounds(node_id)
        selection_bounds = self.scene.selection_bounds()

        self.assertGreater(expanded_payload["height"], collapsed_payload["height"])
        self.assertIsNotNone(node_bounds)
        self.assertIsNotNone(selection_bounds)
        self.assertAlmostEqual(node_bounds.height(), expanded_payload["height"], places=6)
        self.assertAlmostEqual(selection_bounds.height(), expanded_payload["height"], places=6)

    def test_rect_selection_uses_drag_direction_for_enclosed_and_crossing_modes(self) -> None:
        enclosed_node = self.scene.add_node_from_type("core.constant", -140.0, -60.0)
        crossing_node = self.scene.add_node_from_type("core.python_script", 120.0, -60.0)
        retained_node = self.scene.add_node_from_type("core.logger", -140.0, 180.0)

        enclosed_bounds = self.scene.node_bounds(enclosed_node)
        crossing_bounds = self.scene.node_bounds(crossing_node)
        self.assertIsNotNone(enclosed_bounds)
        self.assertIsNotNone(crossing_bounds)
        assert enclosed_bounds is not None
        assert crossing_bounds is not None

        min_x = enclosed_bounds.x() - 24.0
        max_x = crossing_bounds.x() + min(36.0, crossing_bounds.width() * 0.5)
        min_y = min(enclosed_bounds.y(), crossing_bounds.y()) - 24.0
        max_y = max(
            enclosed_bounds.y() + enclosed_bounds.height(),
            crossing_bounds.y() + crossing_bounds.height(),
        ) + 24.0

        self.assertLess(crossing_bounds.x(), max_x)
        self.assertLess(max_x, crossing_bounds.x() + crossing_bounds.width())
        self.assertGreaterEqual(max_x, enclosed_bounds.x() + enclosed_bounds.width())

        self.scene.select_nodes_in_rect(min_x, min_y, max_x, max_y)
        self.assertEqual(set(self.scene.selected_node_lookup), {enclosed_node})

        self.scene.select_nodes_in_rect(max_x, min_y, min_x, max_y)
        self.assertEqual(set(self.scene.selected_node_lookup), {enclosed_node, crossing_node})

        self.scene.select_node(retained_node)
        self.scene.select_nodes_in_rect(max_x, max_y, min_x, min_y, True)
        self.assertEqual(
            set(self.scene.selected_node_lookup),
            {enclosed_node, crossing_node, retained_node},
        )

    def test_minimap_payload_tracks_selection_and_fallback_bounds(self) -> None:
        empty_bounds = self.scene.workspace_scene_bounds_payload
        self.assertAlmostEqual(empty_bounds["x"], -1600.0, places=6)
        self.assertAlmostEqual(empty_bounds["y"], -900.0, places=6)
        self.assertAlmostEqual(empty_bounds["width"], 3200.0, places=6)
        self.assertAlmostEqual(empty_bounds["height"], 1800.0, places=6)
        self.assertEqual(self.scene.minimap_nodes_model, [])

        node_a = self.scene.add_node_from_type("core.constant", 30.0, 40.0)
        node_b = self.scene.add_node_from_type("core.python_script", 390.0, 200.0)
        self.scene.select_node(node_b)

        minimap_payload = {item["node_id"]: item for item in self.scene.minimap_nodes_model}
        self.assertIn(node_a, minimap_payload)
        self.assertIn(node_b, minimap_payload)
        self.assertNotIn("selected", minimap_payload[node_a])
        self.assertNotIn("selected", minimap_payload[node_b])
        self.assertEqual(self.scene.selected_node_lookup, {node_b: True})

        workspace_bounds = self.scene.workspace_scene_bounds_payload
        node_a_bounds = self.scene.node_bounds(node_a)
        node_b_bounds = self.scene.node_bounds(node_b)
        self.assertIsNotNone(node_a_bounds)
        self.assertIsNotNone(node_b_bounds)
        expected_workspace_bounds = node_a_bounds.united(node_b_bounds)
        self.assertLessEqual(workspace_bounds["x"], expected_workspace_bounds.x())
        self.assertLessEqual(workspace_bounds["y"], expected_workspace_bounds.y())
        self.assertGreaterEqual(workspace_bounds["x"] + workspace_bounds["width"], expected_workspace_bounds.x() + expected_workspace_bounds.width())
        self.assertGreaterEqual(
            workspace_bounds["y"] + workspace_bounds["height"],
            expected_workspace_bounds.y() + expected_workspace_bounds.height(),
        )
        self.assertGreaterEqual(workspace_bounds["width"], 3200.0)
        self.assertGreaterEqual(workspace_bounds["height"], 1800.0)

    def test_move_nodes_by_delta_moves_group_with_single_history_entry(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        node_a = self.scene.add_node_from_type("core.constant", 20.0, 30.0)
        node_b = self.scene.add_node_from_type("core.python_script", 360.0, 170.0)
        node_c = self.scene.add_node_from_type("core.constant", 720.0, 260.0)
        node_d = self.scene.add_node_from_type("core.python_script", 980.0, 280.0)
        moved_edge_id = self.scene.connect_nodes(node_a, node_b)
        unrelated_edge_id = self.scene.connect_nodes(node_c, node_d)
        history.clear_workspace(self.workspace_id)
        workspace = self.model.project.workspaces[self.workspace_id]

        before_dx = workspace.nodes[node_b].x - workspace.nodes[node_a].x
        before_dy = workspace.nodes[node_b].y - workspace.nodes[node_a].y
        self.scene.select_node(node_a, False)
        self.scene.select_node(node_b, True)
        selected_lookup = {node_a: True, node_b: True}
        self.assertEqual(self.scene.selected_node_lookup, selected_lookup)

        baseline_nodes = {item["node_id"]: copy.deepcopy(item) for item in self.scene.nodes_model}
        baseline_minimap = {item["node_id"]: copy.deepcopy(item) for item in self.scene.minimap_nodes_model}
        baseline_edges = {item["edge_id"]: copy.deepcopy(item) for item in self.scene.edges_model}
        nodes_changed: list[str] = []
        edges_changed: list[str] = []
        self.scene.nodes_changed.connect(lambda: nodes_changed.append("nodes"))
        self.scene.edges_changed.connect(lambda: edges_changed.append("edges"))
        rebuild_calls: list[str] = []
        original_rebuild_models = self.scene._scene_context.rebuild_models

        def _unexpected_rebuild_models() -> None:
            rebuild_calls.append("rebuild")
            original_rebuild_models()

        self.scene._scene_context.rebuild_models = _unexpected_rebuild_models
        try:
            moved = self.scene.move_nodes_by_delta([node_a, node_b], 55.0, -25.0)
        finally:
            self.scene._scene_context.rebuild_models = original_rebuild_models

        self.assertTrue(moved)
        self.assertEqual(rebuild_calls, [])
        self.assertEqual(nodes_changed, ["nodes"])
        self.assertEqual(edges_changed, ["edges"])
        self.assertEqual(history.undo_depth(self.workspace_id), 1)
        self.assertEqual(self.scene.selected_node_lookup, selected_lookup)
        self.assertAlmostEqual(workspace.nodes[node_a].x, 75.0, places=6)
        self.assertAlmostEqual(workspace.nodes[node_a].y, 5.0, places=6)
        self.assertAlmostEqual(workspace.nodes[node_b].x, 415.0, places=6)
        self.assertAlmostEqual(workspace.nodes[node_b].y, 145.0, places=6)

        after_dx = workspace.nodes[node_b].x - workspace.nodes[node_a].x
        after_dy = workspace.nodes[node_b].y - workspace.nodes[node_a].y
        self.assertAlmostEqual(before_dx, after_dx, places=6)
        self.assertAlmostEqual(before_dy, after_dy, places=6)
        node_payload = {item["node_id"]: item for item in self.scene.nodes_model}
        minimap_payload = {item["node_id"]: item for item in self.scene.minimap_nodes_model}
        edge_payload = {item["edge_id"]: item for item in self.scene.edges_model}
        self.assertAlmostEqual(node_payload[node_a]["x"], 75.0, places=6)
        self.assertAlmostEqual(node_payload[node_a]["y"], 5.0, places=6)
        self.assertAlmostEqual(node_payload[node_b]["x"], 415.0, places=6)
        self.assertAlmostEqual(node_payload[node_b]["y"], 145.0, places=6)
        self.assertAlmostEqual(minimap_payload[node_a]["x"], 75.0, places=6)
        self.assertAlmostEqual(minimap_payload[node_a]["y"], 5.0, places=6)
        self.assertAlmostEqual(minimap_payload[node_b]["x"], 415.0, places=6)
        self.assertAlmostEqual(minimap_payload[node_b]["y"], 145.0, places=6)
        self.assertEqual(node_payload[node_c], baseline_nodes[node_c])
        self.assertEqual(node_payload[node_d], baseline_nodes[node_d])
        self.assertEqual(minimap_payload[node_c], baseline_minimap[node_c])
        self.assertEqual(minimap_payload[node_d], baseline_minimap[node_d])
        self.assertNotEqual(edge_payload[moved_edge_id], baseline_edges[moved_edge_id])
        self.assertEqual(edge_payload[unrelated_edge_id], baseline_edges[unrelated_edge_id])
        edge_delta = self.scene.edge_delta_payload
        self.assertEqual(edge_delta["schema"], "graph_scene_edge_structural_delta")
        self.assertEqual(edge_delta["version"], 1)
        self.assertFalse(edge_delta["requires_full_refresh"])
        self.assertEqual(edge_delta["reason"], "node_position")
        self.assertEqual(edge_delta["added_edge_ids"], [])
        self.assertEqual(edge_delta["updated_edge_ids"], [moved_edge_id])
        self.assertEqual(edge_delta["removed_edge_ids"], [])
        self.assertEqual(edge_delta["dirty_edge_ids"], [moved_edge_id])
        self.assertEqual(edge_delta["dirty_node_ids"], sorted([node_a, node_b]))
        self.assertEqual(edge_delta["removed_node_ids"], [])
        self.assertCountEqual(edge_delta["affected_node_ids"], [node_a, node_b])
        self.assertEqual(edge_delta["edge_count_after"], 2)
        self.assertEqual(edge_delta["added_edges"], [])
        self.assertEqual(edge_delta["removed_edges"], [])
        self.assertEqual(len(edge_delta["updated_edges"]), 1)
        updated_entry = edge_delta["updated_edges"][0]
        self.assertEqual(updated_entry["edge_id"], moved_edge_id)
        self.assertEqual(
            updated_entry["index"],
            [item["edge_id"] for item in self.scene.edges_model].index(moved_edge_id),
        )
        self.assertEqual(updated_entry["payload"]["edge_id"], moved_edge_id)
        self.assertEqual(updated_entry["payload"]["source_node_id"], node_a)
        self.assertEqual(updated_entry["payload"]["target_node_id"], node_b)

        undo_rebuild_calls: list[str] = []
        original_rebuild_models = self.scene._scene_context.rebuild_models

        def _unexpected_undo_rebuild_models() -> None:
            undo_rebuild_calls.append("rebuild")
            original_rebuild_models()

        self.scene._scene_context.rebuild_models = _unexpected_undo_rebuild_models
        try:
            self.assertIsNotNone(history.undo_workspace(self.workspace_id, workspace))
            self.scene.refresh_workspace_from_model(self.workspace_id)
        finally:
            self.scene._scene_context.rebuild_models = original_rebuild_models
        self.assertEqual(undo_rebuild_calls, [])
        self.assertEqual(self.scene.selected_node_lookup, selected_lookup)
        self.assertAlmostEqual(workspace.nodes[node_a].x, 20.0, places=6)
        self.assertAlmostEqual(workspace.nodes[node_a].y, 30.0, places=6)
        self.assertAlmostEqual(workspace.nodes[node_b].x, 360.0, places=6)
        self.assertAlmostEqual(workspace.nodes[node_b].y, 170.0, places=6)
        self.assertEqual(nodes_changed, ["nodes", "nodes"])
        self.assertEqual(edges_changed, ["edges", "edges"])
        self.assertEqual(self.scene.edge_delta_payload["reason"], "node_position")
        self.assertEqual(self.scene.edge_delta_payload["updated_edge_ids"], [moved_edge_id])

        redo_rebuild_calls: list[str] = []
        original_rebuild_models = self.scene._scene_context.rebuild_models

        def _unexpected_redo_rebuild_models() -> None:
            redo_rebuild_calls.append("rebuild")
            original_rebuild_models()

        self.scene._scene_context.rebuild_models = _unexpected_redo_rebuild_models
        try:
            self.assertIsNotNone(history.redo_workspace(self.workspace_id, workspace))
            self.scene.refresh_workspace_from_model(self.workspace_id)
        finally:
            self.scene._scene_context.rebuild_models = original_rebuild_models
        self.assertEqual(redo_rebuild_calls, [])
        self.assertEqual(self.scene.selected_node_lookup, selected_lookup)
        self.assertAlmostEqual(workspace.nodes[node_a].x, 75.0, places=6)
        self.assertAlmostEqual(workspace.nodes[node_a].y, 5.0, places=6)
        self.assertAlmostEqual(workspace.nodes[node_b].x, 415.0, places=6)
        self.assertAlmostEqual(workspace.nodes[node_b].y, 145.0, places=6)
        self.assertEqual(nodes_changed, ["nodes", "nodes", "nodes"])
        self.assertEqual(edges_changed, ["edges", "edges", "edges"])
        self.assertEqual(self.scene.edge_delta_payload["reason"], "node_position")
        self.assertEqual(self.scene.edge_delta_payload["updated_edge_ids"], [moved_edge_id])

    def test_layout_actions_align_and_distribute_selected_nodes_with_grouped_history(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        node_a = self.scene.add_node_from_type("core.constant", 40.0, 20.0)
        node_b = self.scene.add_node_from_type("core.python_script", 320.0, 210.0)
        node_c = self.scene.add_node_from_type("core.logger", 640.0, 80.0)
        workspace = self.model.project.workspaces[self.workspace_id]
        self.scene.select_node(node_a, False)
        self.scene.select_node(node_b, True)
        self.scene.select_node(node_c, True)
        history.clear_workspace(self.workspace_id)

        moved = self.scene.align_selected_nodes("left")
        self.assertTrue(moved)
        self.assertEqual(history.undo_depth(self.workspace_id), 1)

        left_edges = []
        for node_id in (node_a, node_b, node_c):
            bounds = self.scene.node_bounds(node_id)
            self.assertIsNotNone(bounds)
            left_edges.append(bounds.x())
        for left in left_edges[1:]:
            self.assertAlmostEqual(left, left_edges[0], places=6)

        self.assertIsNotNone(history.undo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertAlmostEqual(workspace.nodes[node_a].x, 40.0, places=6)
        self.assertAlmostEqual(workspace.nodes[node_b].x, 320.0, places=6)
        self.assertAlmostEqual(workspace.nodes[node_c].x, 640.0, places=6)

        self.assertIsNotNone(history.redo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertAlmostEqual(workspace.nodes[node_a].x, 40.0, places=6)
        self.assertAlmostEqual(workspace.nodes[node_b].x, 40.0, places=6)
        self.assertAlmostEqual(workspace.nodes[node_c].x, 40.0, places=6)

        self.model.set_node_position(self.workspace_id, node_a, 10.0, 30.0)
        self.model.set_node_position(self.workspace_id, node_b, 290.0, 120.0)
        self.model.set_node_position(self.workspace_id, node_c, 700.0, 260.0)
        self.scene.refresh_workspace_from_model(self.workspace_id)
        history.clear_workspace(self.workspace_id)

        before_sorted = sorted(
            (self.scene.node_bounds(node_id) for node_id in (node_a, node_b, node_c)),
            key=lambda bounds: float(bounds.x()) if bounds is not None else 0.0,
        )
        self.assertTrue(all(bounds is not None for bounds in before_sorted))
        moved = self.scene.distribute_selected_nodes("horizontal")
        self.assertTrue(moved)
        self.assertEqual(history.undo_depth(self.workspace_id), 1)

        after_sorted = sorted(
            (self.scene.node_bounds(node_id) for node_id in (node_a, node_b, node_c)),
            key=lambda bounds: float(bounds.x()) if bounds is not None else 0.0,
        )
        self.assertTrue(all(bounds is not None for bounds in after_sorted))
        first_before = before_sorted[0]
        last_before = before_sorted[-1]
        first_after = after_sorted[0]
        last_after = after_sorted[-1]
        self.assertIsNotNone(first_before)
        self.assertIsNotNone(last_before)
        self.assertIsNotNone(first_after)
        self.assertIsNotNone(last_after)
        self.assertAlmostEqual(first_after.x(), first_before.x(), places=6)
        self.assertAlmostEqual(last_after.x(), last_before.x(), places=6)

        gap_01 = after_sorted[1].x() - (after_sorted[0].x() + after_sorted[0].width())
        gap_12 = after_sorted[2].x() - (after_sorted[1].x() + after_sorted[1].width())
        self.assertAlmostEqual(gap_01, gap_12, places=6)

    def test_layout_actions_snap_to_grid_and_small_selections_are_safe_noops(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        node_a = self.scene.add_node_from_type("core.constant", 13.0, 17.0)
        node_b = self.scene.add_node_from_type("core.python_script", 171.0, 83.0)
        workspace = self.model.project.workspaces[self.workspace_id]
        history.clear_workspace(self.workspace_id)

        self.scene.select_node(node_a, False)
        self.assertFalse(self.scene.align_selected_nodes("left"))
        self.assertFalse(self.scene.distribute_selected_nodes("horizontal"))
        self.assertEqual(history.undo_depth(self.workspace_id), 0)

        self.scene.select_node(node_b, True)
        moved = self.scene.align_selected_nodes("top", snap_to_grid=True)
        self.assertTrue(moved)
        self.assertEqual(history.undo_depth(self.workspace_id), 1)

        for node_id in (node_a, node_b):
            node = workspace.nodes[node_id]
            self.assertAlmostEqual(float(node.x) / 20.0, round(float(node.x) / 20.0), places=6)
            self.assertAlmostEqual(float(node.y) / 20.0, round(float(node.y) / 20.0), places=6)

        self.assertIsNotNone(history.undo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertAlmostEqual(workspace.nodes[node_a].x, 13.0, places=6)
        self.assertAlmostEqual(workspace.nodes[node_a].y, 17.0, places=6)
        self.assertAlmostEqual(workspace.nodes[node_b].x, 171.0, places=6)
        self.assertAlmostEqual(workspace.nodes[node_b].y, 83.0, places=6)

    def test_straighten_selected_connections_aligns_standard_port_centers(self) -> None:
        source_id = self.scene.add_node_from_type("core.constant", 20.0, 20.0)
        target_id = self.scene.add_node_from_type("core.python_script", 360.0, 180.0)
        edge_id = self.scene.add_edge(source_id, "value", target_id, "payload")
        self.scene.select_node(source_id, False)
        self.scene.select_node(target_id, True)

        before_edge = {item["edge_id"]: item for item in self.scene.edges_model}[edge_id]
        self.assertNotAlmostEqual(before_edge["sy"], before_edge["ty"], places=4)

        self.assertTrue(self.scene.straighten_selected_connections())
        after_edge = {item["edge_id"]: item for item in self.scene.edges_model}[edge_id]
        self.assertAlmostEqual(after_edge["sy"], after_edge["ty"], places=4)

    def test_straighten_selected_connections_aligns_passive_cardinal_ports_on_vertical_axis(self) -> None:
        source_id = self.scene.add_node_from_type("passive.flowchart.process", 20.0, 20.0)
        target_id = self.scene.add_node_from_type("passive.flowchart.process", 260.0, 320.0)
        edge_id = self.scene.add_edge(source_id, "bottom", target_id, "top")
        self.scene.select_node(source_id, False)
        self.scene.select_node(target_id, True)

        before_edge = {item["edge_id"]: item for item in self.scene.edges_model}[edge_id]
        self.assertNotAlmostEqual(before_edge["sx"], before_edge["tx"], places=4)

        self.assertTrue(self.scene.straighten_selected_connections())
        after_edge = {item["edge_id"]: item for item in self.scene.edges_model}[edge_id]
        self.assertAlmostEqual(after_edge["sx"], after_edge["tx"], places=4)

    def test_straighten_selected_connections_ignores_external_edges(self) -> None:
        source_id = self.scene.add_node_from_type("core.constant", 20.0, 20.0)
        target_id = self.scene.add_node_from_type("core.python_script", 360.0, 180.0)
        external_id = self.scene.add_node_from_type("core.python_script", 680.0, 420.0)
        internal_edge_id = self.scene.add_edge(source_id, "value", target_id, "payload")
        external_edge_id = self.scene.add_edge(source_id, "as_text", external_id, "payload")
        self.scene.select_node(source_id, False)
        self.scene.select_node(target_id, True)

        self.assertTrue(self.scene.straighten_selected_connections())
        edge_payload = {item["edge_id"]: item for item in self.scene.edges_model}
        self.assertAlmostEqual(edge_payload[internal_edge_id]["sy"], edge_payload[internal_edge_id]["ty"], places=4)
        self.assertNotAlmostEqual(edge_payload[external_edge_id]["sy"], edge_payload[external_edge_id]["ty"], places=4)

    def test_straighten_selected_connections_records_grouped_undo_redo(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        source_id = self.scene.add_node_from_type("core.constant", 20.0, 20.0)
        target_id = self.scene.add_node_from_type("core.python_script", 360.0, 180.0)
        edge_id = self.scene.add_edge(source_id, "value", target_id, "payload")
        workspace = self.model.project.workspaces[self.workspace_id]
        self.scene.select_node(source_id, False)
        self.scene.select_node(target_id, True)
        history.clear_workspace(self.workspace_id)
        before_positions = {
            node_id: (workspace.nodes[node_id].x, workspace.nodes[node_id].y)
            for node_id in (source_id, target_id)
        }

        self.assertTrue(self.scene.straighten_selected_connections())
        self.assertEqual(history.undo_depth(self.workspace_id), 1)
        after_edge = {item["edge_id"]: item for item in self.scene.edges_model}[edge_id]
        self.assertAlmostEqual(after_edge["sy"], after_edge["ty"], places=4)

        self.assertIsNotNone(history.undo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertEqual(
            {
                node_id: (workspace.nodes[node_id].x, workspace.nodes[node_id].y)
                for node_id in (source_id, target_id)
            },
            before_positions,
        )

        self.assertIsNotNone(history.redo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        redone_edge = {item["edge_id"]: item for item in self.scene.edges_model}[edge_id]
        self.assertAlmostEqual(redone_edge["sy"], redone_edge["ty"], places=4)

    def test_duplicate_selected_subgraph_offsets_nodes_and_internal_edges_only(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        source_id = self.scene.add_node_from_type("core.constant", 10.0, 20.0)
        target_id = self.scene.add_node_from_type("core.python_script", 280.0, 40.0)
        external_id = self.scene.add_node_from_type("core.python_script", 520.0, 80.0)
        self.scene.add_edge(source_id, "value", target_id, "payload")
        self.scene.add_edge(source_id, "as_text", external_id, "payload")
        self.scene.select_node(source_id, False)
        self.scene.select_node(target_id, True)
        history.clear_workspace(self.workspace_id)

        duplicated = self.scene.duplicate_selected_subgraph()
        self.assertTrue(duplicated)
        self.assertEqual(history.undo_depth(self.workspace_id), 1)

        workspace = self.model.project.workspaces[self.workspace_id]
        self.assertEqual(len(workspace.nodes), 5)
        self.assertEqual(len(workspace.edges), 3)

        duplicated_ids = [item.node.node_id for item in self.scene.selectedItems()]
        self.assertEqual(len(duplicated_ids), 2)
        self.assertNotIn(source_id, duplicated_ids)
        self.assertNotIn(target_id, duplicated_ids)

        source_node = workspace.nodes[source_id]
        target_node = workspace.nodes[target_id]
        duplicated_source_id = ""
        duplicated_target_id = ""
        for node_id in duplicated_ids:
            node = workspace.nodes[node_id]
            if (
                node.type_id == source_node.type_id
                and node.title == source_node.title
                and abs(node.x - (source_node.x + 40.0)) < 1e-6
                and abs(node.y - (source_node.y + 40.0)) < 1e-6
            ):
                duplicated_source_id = node_id
            if (
                node.type_id == target_node.type_id
                and node.title == target_node.title
                and abs(node.x - (target_node.x + 40.0)) < 1e-6
                and abs(node.y - (target_node.y + 40.0)) < 1e-6
            ):
                duplicated_target_id = node_id
        self.assertTrue(duplicated_source_id)
        self.assertTrue(duplicated_target_id)

        duplicated_internal_edges = [
            edge
            for edge in workspace.edges.values()
            if edge.source_node_id == duplicated_source_id
            and edge.target_node_id == duplicated_target_id
            and edge.source_port_key == "value"
            and edge.target_port_key == "payload"
        ]
        self.assertEqual(len(duplicated_internal_edges), 1)
        duplicated_external_edges = [
            edge
            for edge in workspace.edges.values()
            if edge.source_node_id == duplicated_source_id and edge.source_port_key == "as_text"
        ]
        self.assertEqual(duplicated_external_edges, [])

    def test_paste_subgraph_fragment_centers_selection_and_records_single_history_entry(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        source_id = self.scene.add_node_from_type("core.constant", 10.0, 20.0)
        target_id = self.scene.add_node_from_type("core.python_script", 280.0, 40.0)
        self.scene.add_edge(source_id, "value", target_id, "payload")
        workspace = self.model.project.workspaces[self.workspace_id]
        workspace.nodes[source_id].visual_style = {"fill": "#102030"}
        workspace.nodes[target_id].visual_style = {"fill": "#405060"}
        self.scene.select_node(source_id, False)
        self.scene.select_node(target_id, True)
        fragment = self.scene.serialize_selected_subgraph_fragment()
        self.assertIsNotNone(fragment)
        history.clear_workspace(self.workspace_id)

        nodes_changed: list[str] = []
        edges_changed: list[str] = []
        publication_events: list[str] = []
        rebuild_calls: list[str] = []
        self.scene.nodes_changed.connect(lambda: nodes_changed.append("nodes"))
        self.scene.nodes_changed.connect(lambda: publication_events.append("nodes"))
        self.scene.edges_changed.connect(lambda: edges_changed.append("edges"))
        self.scene.edges_changed.connect(lambda: publication_events.append("edges"))
        self.scene.selection_changed.connect(
            lambda: publication_events.append("selection")
        )
        original_rebuild_models = self.scene._scene_context.rebuild_models

        def _unexpected_rebuild_models() -> None:
            rebuild_calls.append("rebuild")
            original_rebuild_models()

        self.scene._scene_context.rebuild_models = _unexpected_rebuild_models
        try:
            pasted = self.scene.paste_subgraph_fragment(fragment, 620.0, 240.0)
        finally:
            self.scene._scene_context.rebuild_models = original_rebuild_models
        self.assertTrue(pasted)
        self.assertEqual(history.undo_depth(self.workspace_id), 1)
        self.assertEqual(rebuild_calls, [])
        self.assertEqual(nodes_changed, ["nodes"])
        self.assertEqual(edges_changed, ["edges"])
        self.assertEqual(publication_events, ["nodes", "edges", "selection"])

        pasted_ids = [item.node.node_id for item in self.scene.selectedItems()]
        self.assertEqual(len(pasted_ids), 2)
        self.assertEqual({source_id, target_id} & set(pasted_ids), set())
        self.assertEqual(len(workspace.nodes), 4)
        self.assertEqual(len(workspace.edges), 2)
        self.assertTrue(all(workspace.nodes[node_id].visual_style == {} for node_id in pasted_ids))

        selection_bounds = self.scene.selection_bounds()
        self.assertIsNotNone(selection_bounds)
        assert selection_bounds is not None
        self.assertAlmostEqual(selection_bounds.center().x(), 620.0, places=6)
        self.assertAlmostEqual(selection_bounds.center().y(), 240.0, places=6)

        pasted_edge_count = len(
            [
                edge
                for edge in workspace.edges.values()
                if edge.source_node_id in pasted_ids and edge.target_node_id in pasted_ids
            ]
        )
        self.assertEqual(pasted_edge_count, 1)
        pasted_edge_id = next(
            edge.edge_id
            for edge in workspace.edges.values()
            if edge.source_node_id in pasted_ids and edge.target_node_id in pasted_ids
        )
        node_delta = getattr(self.scene.state_bridge, "node_delta_payload", {})
        self.assertEqual(node_delta["reason"], "fragment_addition_delta")
        self.assertEqual(set(node_delta["added_node_ids"]), set(pasted_ids))
        self.assertEqual({payload["node_id"] for payload in node_delta["nodes"]}, set(pasted_ids))
        edge_delta = self.scene.edge_delta_payload
        self.assertEqual(edge_delta["reason"], "fragment_addition_delta")
        self.assertEqual(edge_delta["added_edge_ids"], [pasted_edge_id])
        self.assertEqual(edge_delta["updated_edge_ids"], [])
        self.assertEqual(edge_delta["removed_edge_ids"], [])
        self.assertEqual(edge_delta["added_edges"][0]["payload"]["edge_id"], pasted_edge_id)

        self.assertIsNotNone(history.undo_workspace(self.workspace_id, workspace))
        self.scene.refresh_workspace_from_model(self.workspace_id)
        self.assertEqual(len(workspace.nodes), 2)
        self.assertEqual(len(workspace.edges), 1)

    def test_duplicate_selected_subgraph_treats_selected_subnode_shell_as_subtree_root(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        shell_id = self.scene.add_node_from_type("core.subnode", 120.0, 80.0)
        nested_script_id = self.scene.add_node_from_type("core.python_script", 320.0, 120.0)
        nested_constant_id = self.scene.add_node_from_type("core.constant", 80.0, 220.0)
        deep_script_id = self.scene.add_node_from_type("core.python_script", 520.0, 260.0)
        external_logger_id = self.scene.add_node_from_type("core.logger", 780.0, 140.0)
        workspace = self.model.project.workspaces[self.workspace_id]
        workspace.nodes[nested_script_id].parent_node_id = shell_id
        workspace.nodes[nested_constant_id].parent_node_id = shell_id
        workspace.nodes[deep_script_id].parent_node_id = nested_script_id
        self.scene.refresh_workspace_from_model(self.workspace_id)

        self.model.add_edge(self.workspace_id, nested_constant_id, "as_text", nested_script_id, "payload")
        self.model.add_edge(self.workspace_id, nested_script_id, "result", deep_script_id, "payload")
        self.model.add_edge(self.workspace_id, nested_constant_id, "value", external_logger_id, "message")
        self.scene.refresh_workspace_from_model(self.workspace_id)

        original_subtree = subtree_node_ids(workspace, [shell_id])
        original_subtree_set = set(original_subtree)
        original_internal_edge_count = len(
            [
                edge
                for edge in workspace.edges.values()
                if edge.source_node_id in original_subtree_set and edge.target_node_id in original_subtree_set
            ]
        )

        self.scene.select_node(shell_id, False)
        history.clear_workspace(self.workspace_id)
        duplicated = self.scene.duplicate_selected_subgraph()
        self.assertTrue(duplicated)
        self.assertEqual(history.undo_depth(self.workspace_id), 1)

        duplicated_shell_ids = [
            node_id
            for node_id, node in workspace.nodes.items()
            if node.type_id == "core.subnode"
            and node.parent_node_id is None
            and node_id != shell_id
            and abs(float(node.x) - (float(workspace.nodes[shell_id].x) + 40.0)) < 1e-6
            and abs(float(node.y) - (float(workspace.nodes[shell_id].y) + 40.0)) < 1e-6
        ]
        self.assertEqual(len(duplicated_shell_ids), 1)
        duplicated_shell_id = duplicated_shell_ids[0]

        duplicated_subtree = subtree_node_ids(workspace, [duplicated_shell_id])
        duplicated_subtree_set = set(duplicated_subtree)
        self.assertEqual(len(duplicated_subtree), len(original_subtree))
        self.assertEqual(original_subtree_set & duplicated_subtree_set, set())

        duplicated_internal_edge_count = len(
            [
                edge
                for edge in workspace.edges.values()
                if edge.source_node_id in duplicated_subtree_set and edge.target_node_id in duplicated_subtree_set
            ]
        )
        self.assertEqual(duplicated_internal_edge_count, original_internal_edge_count)

        duplicated_external_edges = [
            edge
            for edge in workspace.edges.values()
            if (
                edge.source_node_id in duplicated_subtree_set and edge.target_node_id not in duplicated_subtree_set
            )
            or (
                edge.target_node_id in duplicated_subtree_set and edge.source_node_id not in duplicated_subtree_set
            )
        ]
        self.assertEqual(duplicated_external_edges, [])

    def test_focus_move_and_connect_are_restricted_to_active_scope(self) -> None:
        shell_id = self.scene.add_node_from_type("core.subnode", 180.0, 120.0)
        root_source_id = self.scene.add_node_from_type("core.constant", 40.0, 40.0)
        nested_logger_id = self.scene.add_node_from_type("core.logger", 120.0, 80.0)
        nested_target_id = self.scene.add_node_from_type("core.python_script", 340.0, 100.0)
        workspace = self.model.project.workspaces[self.workspace_id]
        workspace.nodes[nested_logger_id].parent_node_id = shell_id
        workspace.nodes[nested_target_id].parent_node_id = shell_id
        self.scene.refresh_workspace_from_model(self.workspace_id)

        self.assertIsNone(self.scene.focus_node(nested_logger_id))
        self.assertFalse(self.scene.move_nodes_by_delta([nested_logger_id], 40.0, 25.0))
        self.assertAlmostEqual(workspace.nodes[nested_logger_id].x, 120.0, places=6)
        self.assertAlmostEqual(workspace.nodes[nested_logger_id].y, 80.0, places=6)

        with self.assertRaises(ValueError):
            self.scene.add_edge(root_source_id, "as_text", nested_logger_id, "message")

        self.assertTrue(self.scene.open_scope_for_node(nested_logger_id))
        focused_center = self.scene.focus_node(nested_logger_id)
        self.assertIsNotNone(focused_center)
        self.assertEqual(self.scene.active_scope_path, [shell_id])
        self.assertTrue(self.scene.move_nodes_by_delta([nested_logger_id, nested_target_id], 15.0, -10.0))

    def test_group_selected_nodes_creates_subnode_pins_and_single_history_entry(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        source_id = self.scene.add_node_from_type("core.constant", 20.0, 40.0)
        grouped_if_id = self.scene.add_node_from_type("core.if", 320.0, 60.0)
        grouped_constant_id = self.scene.add_node_from_type("core.constant", 220.0, 190.0)
        target_id = self.scene.add_node_from_type("core.python_script", 640.0, 90.0)
        external_script_id = self.scene.add_node_from_type("core.python_script", 700.0, 230.0)

        self.scene.add_edge(source_id, "value", grouped_if_id, "condition")
        self.scene.add_edge(grouped_constant_id, "as_text", grouped_if_id, "true_value")
        self.scene.add_edge(grouped_if_id, "result", target_id, "payload")
        self.scene.add_edge(grouped_constant_id, "value", external_script_id, "payload")
        workspace = self.model.project.workspaces[self.workspace_id]

        self.scene.select_node(grouped_if_id, False)
        self.scene.select_node(grouped_constant_id, True)
        history.clear_workspace(self.workspace_id)

        grouped = self.scene.group_selected_nodes()
        self.assertTrue(grouped)
        self.assertEqual(history.undo_depth(self.workspace_id), 1)

        shell_id = self.scene.selected_node_id()
        self.assertIsNotNone(shell_id)
        assert shell_id is not None
        shell_node = workspace.nodes[shell_id]
        self.assertEqual(shell_node.type_id, "core.subnode")
        self.assertIsNone(shell_node.parent_node_id)
        self.assertEqual(workspace.nodes[grouped_if_id].parent_node_id, shell_id)
        self.assertEqual(workspace.nodes[grouped_constant_id].parent_node_id, shell_id)

        pin_ids = [
            node_id
            for node_id, node in workspace.nodes.items()
            if node.parent_node_id == shell_id and node.type_id in {"core.subnode_input", "core.subnode_output"}
        ]
        self.assertEqual(len(pin_ids), 3)
        shell_payload = next(item for item in self.scene.nodes_model if item["node_id"] == shell_id)
        shell_port_labels = {str(port.get("label", "")) for port in shell_payload["ports"]}
        self.assertEqual(shell_port_labels, {"condition", "result", "value"})

        grouped_ids = {grouped_if_id, grouped_constant_id}
        outer_ids = {source_id, target_id, external_script_id}
        for edge in workspace.edges.values():
            self.assertFalse(edge.source_node_id in outer_ids and edge.target_node_id in grouped_ids)
            self.assertFalse(edge.source_node_id in grouped_ids and edge.target_node_id in outer_ids)

        edge_tuples = {
            (edge.source_node_id, edge.source_port_key, edge.target_node_id, edge.target_port_key)
            for edge in workspace.edges.values()
        }
        incoming_shell_edges = [edge for edge in edge_tuples if edge[0] == source_id and edge[2] == shell_id]
        self.assertEqual(len(incoming_shell_edges), 1)
        outgoing_shell_target_edges = [edge for edge in edge_tuples if edge[0] == shell_id and edge[2] == target_id]
        self.assertEqual(len(outgoing_shell_target_edges), 1)
        outgoing_shell_script_edges = [
            edge
            for edge in edge_tuples
            if edge[0] == shell_id and edge[2] == external_script_id and edge[3] == "payload"
        ]
        self.assertEqual(len(outgoing_shell_script_edges), 1)

    def test_group_selected_nodes_orders_outgoing_shell_ports_by_external_target_geometry(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        branch_id = self.scene.add_node_from_type("core.stream_gate", 260.0, 80.0)
        constant_id = self.scene.add_node_from_type("core.constant", 120.0, 120.0)
        top_end_id = self.scene.add_node_from_type("core.python_script", 760.0, 20.0)
        bottom_end_id = self.scene.add_node_from_type("core.python_script", 760.0, 340.0)
        self.scene.add_edge(constant_id, "value", branch_id, "gate")
        self.scene.add_edge(branch_id, "output_0", top_end_id, "payload")
        self.scene.add_edge(branch_id, "output_1", bottom_end_id, "payload")
        workspace = self.model.project.workspaces[self.workspace_id]

        self.scene.select_node(branch_id, False)
        self.scene.select_node(constant_id, True)
        history.clear_workspace(self.workspace_id)
        self.assertTrue(self.scene.group_selected_nodes())
        self.assertEqual(history.undo_depth(self.workspace_id), 1)

        shell_id = self.scene.selected_node_id()
        self.assertIsNotNone(shell_id)
        assert shell_id is not None
        shell_payload = next(item for item in self.scene.nodes_model if item["node_id"] == shell_id)
        shell_port_keys = [str(port["key"]) for port in shell_payload["ports"]]

        target_y_by_port: dict[str, float] = {}
        for edge in workspace.edges.values():
            if edge.source_node_id != shell_id:
                continue
            if edge.source_port_key not in shell_port_keys:
                continue
            target_y_by_port[edge.source_port_key] = float(workspace.nodes[edge.target_node_id].y)

        ordered_target_y = [target_y_by_port[port_key] for port_key in shell_port_keys]
        self.assertEqual(ordered_target_y, sorted(ordered_target_y))

    def test_ungroup_selected_subnode_restores_wiring_and_single_history_entry(self) -> None:
        self.scene.bind_runtime_history(RuntimeGraphHistory())
        source_id = self.scene.add_node_from_type("core.constant", 20.0, 40.0)
        grouped_if_id = self.scene.add_node_from_type("core.if", 320.0, 60.0)
        grouped_constant_id = self.scene.add_node_from_type("core.constant", 220.0, 190.0)
        target_id = self.scene.add_node_from_type("core.python_script", 640.0, 90.0)
        external_script_id = self.scene.add_node_from_type("core.python_script", 700.0, 230.0)

        self.scene.add_edge(source_id, "value", grouped_if_id, "condition")
        self.scene.add_edge(grouped_constant_id, "as_text", grouped_if_id, "true_value")
        self.scene.add_edge(grouped_if_id, "result", target_id, "payload")
        self.scene.add_edge(grouped_constant_id, "value", external_script_id, "payload")
        workspace = self.model.project.workspaces[self.workspace_id]
        expected_edges = {
            (source_id, "value", grouped_if_id, "condition"),
            (grouped_constant_id, "as_text", grouped_if_id, "true_value"),
            (grouped_if_id, "result", target_id, "payload"),
            (grouped_constant_id, "value", external_script_id, "payload"),
        }

        self.scene.select_node(grouped_if_id, False)
        self.scene.select_node(grouped_constant_id, True)
        self.assertTrue(self.scene.group_selected_nodes())

        shell_id = self.scene.selected_node_id()
        self.assertIsNotNone(shell_id)
        assert shell_id is not None
        pin_ids_before = {
            node_id
            for node_id, node in workspace.nodes.items()
            if node.parent_node_id == shell_id and node.type_id in {"core.subnode_input", "core.subnode_output"}
        }
        self.assertTrue(pin_ids_before)

        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        history.clear_workspace(self.workspace_id)

        self.scene.select_node(shell_id, False)
        ungrouped = self.scene.ungroup_selected_subnode()
        self.assertTrue(ungrouped)
        self.assertEqual(history.undo_depth(self.workspace_id), 1)

        self.assertNotIn(shell_id, workspace.nodes)
        for pin_id in pin_ids_before:
            self.assertNotIn(pin_id, workspace.nodes)
        self.assertEqual(workspace.nodes[grouped_if_id].parent_node_id, None)
        self.assertEqual(workspace.nodes[grouped_constant_id].parent_node_id, None)

        edge_tuples = {
            (edge.source_node_id, edge.source_port_key, edge.target_node_id, edge.target_port_key)
            for edge in workspace.edges.values()
        }
        self.assertEqual(edge_tuples, expected_edges)

    def test_group_selected_nodes_rejects_mixed_scope_selection(self) -> None:
        root_node_id = self.scene.add_node_from_type("core.constant", 40.0, 40.0)
        shell_id = self.scene.add_node_from_type("core.subnode", 260.0, 120.0)
        nested_node_id = self.scene.add_node_from_type("core.logger", 280.0, 180.0)
        workspace = self.model.project.workspaces[self.workspace_id]
        workspace.nodes[nested_node_id].parent_node_id = shell_id
        self.scene.refresh_workspace_from_model(self.workspace_id)

        self.scene._selected_node_ids = [root_node_id, nested_node_id]
        self.assertFalse(self.scene.group_selected_nodes())
        self.assertEqual(
            len([node for node in workspace.nodes.values() if node.type_id == "core.subnode"]),
            1,
        )
__all__ = ['GraphSceneBridgeTrackBTests']
