from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.ui.graph_interactions import GraphInteractions
from ea_node_editor.ui_qml.graph_geometry.surface_contract import STANDARD_COLLAPSED_WIDTH
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from ea_node_editor.ui_qml.graph_surface_metrics import node_surface_metrics
GROUP_BACKDROP_TYPE_ID = "passive.annotation.group_backdrop"
STICKY_NOTE_TYPE_ID = "passive.annotation.sticky_note"
_EXPECTED_CARDINAL_PASSIVE_PORTS = (
    ("top", "neutral", "flow", "flow", "top", True),
    ("right", "neutral", "flow", "flow", "right", True),
    ("bottom", "neutral", "flow", "flow", "bottom", True),
    ("left", "neutral", "flow", "flow", "left", True),
)


def _port_signature(port: object) -> tuple[object, object, object, object, object, object]:
    if isinstance(port, dict):
        return (
            port.get("key"),
            port.get("direction"),
            port.get("kind"),
            port.get("data_type"),
            port.get("side"),
            port.get("allow_multiple_connections"),
        )
    return (
        getattr(port, "key"),
        getattr(port, "direction"),
        getattr(port, "kind"),
        getattr(port, "data_type"),
        getattr(port, "side"),
        getattr(port, "allow_multiple_connections"),
    )


class GroupBackdropCatalogTests(unittest.TestCase):
    def test_generated_js_surface_metric_contract_matches_authoritative_json(self) -> None:
        graph_dir = Path(__file__).resolve().parents[1] / "ea_node_editor" / "ui_qml" / "components" / "graph"
        json_payload = json.loads((graph_dir / "GraphNodeSurfaceMetricContract.json").read_text(encoding="utf-8"))
        js_text = (graph_dir / "GraphNodeSurfaceMetricContract.js").read_text(encoding="utf-8")
        match = re.search(
            r"var SURFACE_METRIC_CONTRACT = (\{.*\});\s*function contract",
            js_text,
            re.DOTALL,
        )

        self.assertIsNotNone(match)
        assert match is not None
        js_payload = json.loads(match.group(1))
        self.assertEqual(js_payload, json_payload)

    def test_default_registry_registers_locked_group_backdrop_spec(self) -> None:
        registry = build_default_registry()
        spec = registry.get_spec(GROUP_BACKDROP_TYPE_ID)

        self.assertEqual(spec.display_name, "Group")
        self.assertEqual(spec.category_path, ("Utilities", "Canvas"))
        self.assertEqual(spec.category, "Utilities > Canvas")
        self.assertEqual(spec.runtime_behavior, "passive")
        self.assertEqual(spec.surface_family, "group_backdrop")
        self.assertEqual(spec.surface_variant, "group_backdrop")
        self.assertTrue(spec.collapsible)
        self.assertEqual(tuple(_port_signature(port) for port in spec.ports), _EXPECTED_CARDINAL_PASSIVE_PORTS)
        self.assertEqual(tuple(prop.key for prop in spec.properties), ("title",))

        title = spec.properties[0]
        self.assertEqual(title.default, "")
        self.assertFalse(title.inspector_visible)
        self.assertEqual(title.inspector_editor, "")
        retired_type_id = "passive.annotation." + "comment" + "_backdrop"
        self.assertIsNone(registry.spec_or_none(retired_type_id))

    def test_group_backdrop_surface_metrics_use_locked_defaults(self) -> None:
        registry = build_default_registry()
        spec = registry.get_spec(GROUP_BACKDROP_TYPE_ID)
        node = NodeInstance(
            node_id="node_group_backdrop",
            type_id=spec.type_id,
            title="",
            x=40.0,
            y=30.0,
        )

        metrics = node_surface_metrics(node, spec, {node.node_id: node})

        self.assertEqual(metrics.default_width, 420.0)
        self.assertEqual(metrics.default_height, 260.0)
        self.assertEqual(metrics.min_width, 260.0)
        self.assertEqual(metrics.min_height, 180.0)
        self.assertGreaterEqual(metrics.collapsed_width, STANDARD_COLLAPSED_WIDTH)
        self.assertEqual(metrics.title_top, 14.0)
        self.assertEqual(metrics.title_height, 24.0)
        self.assertEqual(metrics.body_top, 52.0)
        self.assertEqual(metrics.body_height, 190.0)
        self.assertEqual(metrics.body_left_margin, 18.0)
        self.assertEqual(metrics.body_right_margin, 18.0)
        self.assertEqual(metrics.body_bottom_margin, 18.0)
        self.assertNotIn("show_header_background", metrics.to_payload())
        self.assertNotIn("show_accent_bar", metrics.to_payload())
        self.assertFalse(metrics.use_host_chrome)

    def test_group_backdrop_collapsed_width_expands_to_fit_custom_title(self) -> None:
        registry = build_default_registry()
        spec = registry.get_spec(GROUP_BACKDROP_TYPE_ID)
        node = NodeInstance(
            node_id="node_group_backdrop_long_title",
            type_id=spec.type_id,
            title="Tabular Plot Showcase Direct",
            x=40.0,
            y=30.0,
        )
        default_node = NodeInstance(
            node_id="node_group_backdrop_default_title",
            type_id=spec.type_id,
            title="",
            x=40.0,
            y=30.0,
        )

        metrics = node_surface_metrics(node, spec, {node.node_id: node})
        default_metrics = node_surface_metrics(default_node, spec, {default_node.node_id: default_node})

        self.assertGreater(metrics.collapsed_width, STANDARD_COLLAPSED_WIDTH)
        self.assertGreater(metrics.collapsed_width, default_metrics.collapsed_width)

    def test_group_backdrop_collapsed_width_reserves_shared_title_icon_size(self) -> None:
        registry = build_default_registry()
        spec = registry.get_spec(GROUP_BACKDROP_TYPE_ID)
        node = NodeInstance(
            node_id="node_group_backdrop_title_icon_size",
            type_id=spec.type_id,
            title="Tabular Plot Showcase Direct",
            x=40.0,
            y=30.0,
        )

        baseline_metrics = node_surface_metrics(
            node,
            spec,
            {node.node_id: node},
            graph_label_pixel_size=16,
            graph_node_icon_pixel_size=14,
        )
        shared_icon_metrics = node_surface_metrics(
            node,
            spec,
            {node.node_id: node},
            graph_label_pixel_size=16,
            graph_node_icon_pixel_size=16,
        )

        self.assertAlmostEqual(shared_icon_metrics.collapsed_width - baseline_metrics.collapsed_width, 2.0)

    def test_scene_bridge_payload_and_serializer_roundtrip_stay_on_normal_document_path(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)

        node_id = scene.add_node_from_type(GROUP_BACKDROP_TYPE_ID, 40.0, 60.0)

        self.assertNotIn(node_id, {item["node_id"] for item in scene.nodes_model})

        payload = next(item for item in scene.backdrop_nodes_model if item["node_id"] == node_id)
        self.assertEqual(payload["runtime_behavior"], "passive")
        self.assertEqual(payload["surface_family"], "group_backdrop")
        self.assertEqual(payload["surface_variant"], "group_backdrop")
        self.assertEqual(tuple(_port_signature(port) for port in payload["ports"]), _EXPECTED_CARDINAL_PASSIVE_PORTS)
        self.assertFalse(any(port["connected"] for port in payload["ports"]))
        self.assertEqual(payload["width"], 420.0)
        self.assertEqual(payload["height"], 260.0)
        self.assertFalse(payload["surface_metrics"]["use_host_chrome"])

        serializer = JsonProjectSerializer(registry)
        document = serializer.to_document(model.project)
        workspace_doc = next(doc for doc in document["workspaces"] if doc["workspace_id"] == workspace_id)
        node_doc = next(doc for doc in workspace_doc["nodes"] if doc["node_id"] == node_id)

        self.assertEqual(node_doc["type_id"], GROUP_BACKDROP_TYPE_ID)
        self.assertEqual(node_doc["title"], "")
        self.assertEqual(node_doc["properties"], {"title": ""})
        for membership_key in (
            "member_ids",
            "member_node_ids",
            "member_backdrop_ids",
            "contained_node_ids",
            "contained_backdrop_ids",
        ):
            self.assertNotIn(membership_key, node_doc)

        round_tripped = serializer.from_document(document)
        round_trip_workspace = round_tripped.workspaces[workspace_id]
        round_trip_node = round_trip_workspace.nodes[node_id]
        self.assertEqual(round_trip_node.type_id, GROUP_BACKDROP_TYPE_ID)
        self.assertEqual(round_trip_node.title, "")
        self.assertEqual(round_trip_node.properties, {"title": ""})

    def test_group_backdrop_ports_connect_to_passive_nodes_while_staying_on_backdrop_model(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace_id = model.active_workspace.workspace_id
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace_id)

        backdrop_id = scene.add_node_from_type(GROUP_BACKDROP_TYPE_ID, 40.0, 60.0)
        sticky_id = scene.add_node_from_type(STICKY_NOTE_TYPE_ID, 520.0, 80.0)

        result = GraphInteractions(scene, registry).connect_ports(backdrop_id, "right", sticky_id, "left")

        self.assertTrue(result.ok, result.message)
        self.assertNotIn(backdrop_id, {item["node_id"] for item in scene.nodes_model})
        self.assertIn(backdrop_id, {item["node_id"] for item in scene.backdrop_nodes_model})

        backdrop_payload = next(item for item in scene.backdrop_nodes_model if item["node_id"] == backdrop_id)
        sticky_payload = next(item for item in scene.nodes_model if item["node_id"] == sticky_id)
        backdrop_ports = {port["key"]: port for port in backdrop_payload["ports"]}
        sticky_ports = {port["key"]: port for port in sticky_payload["ports"]}

        self.assertTrue(backdrop_ports["right"]["connected"])
        self.assertEqual(backdrop_ports["right"]["connection_count"], 1)
        self.assertTrue(sticky_ports["left"]["connected"])
        self.assertEqual(sticky_ports["left"]["connection_count"], 1)




if __name__ == "__main__":
    unittest.main()
