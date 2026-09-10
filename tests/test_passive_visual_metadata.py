from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.transforms import build_subnode_custom_workflow_snapshot_data
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.decorators import in_port, node_type, out_port
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge


@node_type(
    type_id="tests.passive_note",
    display_name="Passive Note",
    category_path=("Tests",),
    icon="note",
    ports=(
        in_port("flow_in", kind="flow"),
        out_port("flow_out", kind="flow"),
    ),
    properties=(),
    runtime_behavior="passive",
    surface_family="annotation",
    surface_variant="sticky_note",
)
class _PassiveNotePlugin:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={})


class _PassiveIconPlugin:
    def __init__(self, spec: NodeTypeSpec) -> None:
        self._spec = spec

    def spec(self) -> NodeTypeSpec:
        return self._spec

    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={})


def _build_registry() -> NodeRegistry:
    registry = build_default_registry()
    registry.register(_PassiveNotePlugin)
    return registry


class PassiveVisualMetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = _build_registry()
        self.model = GraphModel()
        self.workspace = self.model.active_workspace
        self.scene = GraphSceneBridge()
        self.scene.set_workspace(self.model, self.registry, self.workspace.workspace_id)

    def _create_labeled_flow_edge(self) -> tuple[str, str, str]:
        source_id = self.scene.add_node_from_type("tests.passive_note", 10.0, 20.0)
        target_id = self.scene.add_node_from_type("tests.passive_note", 280.0, 80.0)
        edge_id = self.scene.add_edge(source_id, "flow_out", target_id, "flow_in")
        self.scene.set_node_visual_style(
            source_id,
            {"fill": "#ffeaa7", "outline": {"width": 2}},
        )
        self.scene.set_edge_label(edge_id, "Primary path")
        self.scene.set_edge_visual_style(
            edge_id,
            {"stroke": "dashed", "arrow": {"kind": "none"}},
        )
        return source_id, target_id, edge_id

    def test_passive_scene_payloads_publish_visual_metadata(self) -> None:
        source_id, target_id, edge_id = self._create_labeled_flow_edge()

        node_payload = {item["node_id"]: item for item in self.scene.nodes_model}
        edge_payload = {item["edge_id"]: item for item in self.scene.edges_model}

        self.assertEqual(node_payload[source_id]["runtime_behavior"], "passive")
        self.assertEqual(node_payload[source_id]["surface_family"], "annotation")
        self.assertEqual(node_payload[source_id]["surface_variant"], "sticky_note")
        self.assertEqual(
            node_payload[source_id]["visual_style"],
            {"fill": "#ffeaa7", "outline": {"width": 2}},
        )
        self.assertEqual(edge_payload[edge_id]["label"], "Primary path")
        self.assertEqual(
            edge_payload[edge_id]["visual_style"],
            {"stroke": "dashed", "arrow": {"kind": "none"}},
        )
        self.assertEqual(edge_payload[edge_id]["source_port_kind"], "flow")
        self.assertEqual(edge_payload[edge_id]["target_port_kind"], "flow")

    def test_title_icon_source_stays_empty_for_passive_payloads_with_valid_icon_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            icon_path = Path(temp_dir) / "passive.svg"
            icon_path.write_bytes(b"icon")
            spec = NodeTypeSpec(
                type_id="tests.title_icon.passive_visual",
                display_name="Passive Visual",
                category_path=("Tests",),
                icon=str(icon_path),
                ports=(PortSpec("flow_out", "out", "flow", "flow"),),
                properties=(),
                runtime_behavior="passive",
                surface_family="annotation",
            )
            self.registry.register_descriptor(spec, lambda: _PassiveIconPlugin(spec))

            node_id = self.scene.add_node_from_type(spec.type_id, 40.0, 60.0)
            node_payload = {item["node_id"]: item for item in self.scene.nodes_model}

            self.assertEqual(node_payload[node_id]["runtime_behavior"], "passive")
            self.assertEqual(node_payload[node_id]["icon_source"], "")

    def test_visual_metadata_mutation_apis_normalize_and_history_roundtrip(self) -> None:
        history = RuntimeGraphHistory()
        self.scene.bind_runtime_history(history)
        source_id = self.scene.add_node_from_type("tests.passive_note", 20.0, 20.0)
        target_id = self.scene.add_node_from_type("tests.passive_note", 280.0, 80.0)
        edge_id = self.scene.add_edge(source_id, "flow_out", target_id, "flow_in")
        history.clear_workspace(self.workspace.workspace_id)

        self.assertEqual(self.scene.normalize_edge_label("  Primary path  "), "Primary path")
        self.assertEqual(self.scene.normalize_node_visual_style(["bad"]), {})
        self.assertEqual(self.scene.normalize_edge_visual_style(None), {})

        self.scene.set_node_visual_style(source_id, {"fill": "#74b9ff"})
        self.assertEqual(self.workspace.nodes[source_id].visual_style, {"fill": "#74b9ff"})
        self.assertEqual(history.undo_depth(self.workspace.workspace_id), 1)

        self.assertIsNotNone(history.undo_workspace(self.workspace.workspace_id, self.workspace))
        self.scene.refresh_workspace_from_model(self.workspace.workspace_id)
        self.assertEqual(self.workspace.nodes[source_id].visual_style, {})
        self.assertIsNotNone(history.redo_workspace(self.workspace.workspace_id, self.workspace))
        self.scene.refresh_workspace_from_model(self.workspace.workspace_id)
        self.assertEqual(self.workspace.nodes[source_id].visual_style, {"fill": "#74b9ff"})

        history.clear_workspace(self.workspace.workspace_id)
        self.scene.set_edge_label(edge_id, "  Branch A  ")
        self.scene.set_edge_visual_style(edge_id, {"stroke": "dotted"})
        self.assertEqual(self.workspace.edges[edge_id].label, "Branch A")
        self.assertEqual(self.workspace.edges[edge_id].visual_style, {"stroke": "dotted"})
        self.assertEqual(history.undo_depth(self.workspace.workspace_id), 2)

        self.assertIsNotNone(history.undo_workspace(self.workspace.workspace_id, self.workspace))
        self.scene.refresh_workspace_from_model(self.workspace.workspace_id)
        self.assertEqual(self.workspace.edges[edge_id].visual_style, {})
        self.assertIsNotNone(history.undo_workspace(self.workspace.workspace_id, self.workspace))
        self.scene.refresh_workspace_from_model(self.workspace.workspace_id)
        self.assertEqual(self.workspace.edges[edge_id].label, "")

        history.clear_workspace(self.workspace.workspace_id)
        self.scene.set_node_visual_style(source_id, {"fill": "#00cec9"})
        self.scene.set_edge_label(edge_id, "Loop back")
        self.scene.set_edge_visual_style(edge_id, {"stroke": "double"})
        self.scene.clear_node_visual_style(source_id)
        self.scene.clear_edge_label(edge_id)
        self.scene.clear_edge_visual_style(edge_id)
        self.assertEqual(self.workspace.nodes[source_id].visual_style, {})
        self.assertEqual(self.workspace.edges[edge_id].label, "")
        self.assertEqual(self.workspace.edges[edge_id].visual_style, {})

    def test_fragment_duplicate_and_custom_workflow_snapshot_preserve_visual_metadata(self) -> None:
        source_id, target_id, edge_id = self._create_labeled_flow_edge()
        self.model.set_node_size(self.workspace.workspace_id, source_id, 360.0, 240.0)
        self.scene.select_node(source_id, False)
        self.scene.select_node(
            next(
                node_id
                for node_id in self.workspace.nodes
                if node_id != source_id
            ),
            True,
        )

        fragment = self.scene.serialize_selected_subgraph_fragment()
        self.assertIsNotNone(fragment)
        assert fragment is not None
        fragment_node = next(node for node in fragment["nodes"] if node["ref_id"] == source_id)
        self.assertEqual(fragment_node["visual_style"], {"fill": "#ffeaa7", "outline": {"width": 2}})
        self.assertEqual(fragment_node["custom_width"], 360.0)
        self.assertEqual(fragment_node["custom_height"], 240.0)
        self.assertEqual(fragment["edges"][0]["label"], "Primary path")
        self.assertEqual(
            fragment["edges"][0]["visual_style"],
            {"stroke": "dashed", "arrow": {"kind": "none"}},
        )

        self.assertTrue(self.scene.duplicate_selected_subgraph())
        duplicated_ids = [item.node.node_id for item in self.scene.selectedItems()]
        duplicated_edges = [
            edge
            for edge in self.workspace.edges.values()
            if edge.source_node_id in duplicated_ids and edge.target_node_id in duplicated_ids
        ]
        self.assertEqual(len(duplicated_edges), 1)
        self.assertEqual(duplicated_edges[0].label, "Primary path")
        self.assertEqual(
            duplicated_edges[0].visual_style,
            {"stroke": "dashed", "arrow": {"kind": "none"}},
        )
        duplicated_source = next(
            node
            for node_id, node in self.workspace.nodes.items()
            if node_id in duplicated_ids and node.visual_style == {"fill": "#ffeaa7", "outline": {"width": 2}}
        )
        self.assertEqual(duplicated_source.visual_style, {"fill": "#ffeaa7", "outline": {"width": 2}})
        self.assertEqual(duplicated_source.custom_width, 360.0)
        self.assertEqual(duplicated_source.custom_height, 240.0)

        shell_id = self.scene.add_node_from_type("core.subnode", 520.0, 40.0)
        source_node = self.workspace.nodes[source_id]
        self.workspace.nodes[source_id].parent_node_id = shell_id
        self.workspace.nodes[target_id].parent_node_id = shell_id
        self.scene.refresh_workspace_from_model(self.workspace.workspace_id)

        snapshot = build_subnode_custom_workflow_snapshot_data(
            workspace=self.workspace,
            registry=self.registry,
            shell_node_id=shell_id,
        )
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        snapshot_node = next(node for node in snapshot["fragment"]["nodes"] if node["ref_id"] == source_id)
        self.assertEqual(
            snapshot_node["visual_style"],
            source_node.visual_style,
        )
        self.assertEqual(snapshot_node["custom_width"], 360.0)
        self.assertEqual(snapshot_node["custom_height"], 240.0)
        self.assertEqual(snapshot["fragment"]["edges"][0]["label"], "Primary path")
        self.assertEqual(
            snapshot["fragment"]["edges"][0]["visual_style"],
            {"stroke": "dashed", "arrow": {"kind": "none"}},
        )


if __name__ == "__main__":
    unittest.main()
