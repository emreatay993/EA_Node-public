from __future__ import annotations

import copy
import unittest
from unittest import mock

import ea_node_editor.graph.invariant_kernel as invariant_kernel
from ea_node_editor.execution.compiler import (
    compile_runtime_snapshot,
    compile_runtime_workspace,
    compile_workspace_document,
)
from ea_node_editor.execution.runtime_dto import RuntimeWorkspace
from ea_node_editor.execution.runtime_snapshot import RuntimeSnapshot, build_runtime_snapshot
from ea_node_editor.graph.effective_ports import effective_ports
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.registry_normalization import normalize_project_for_registry
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.builtins.excalidraw import (
    EXCALIDRAW_BOARD_TYPE_ID,
    EXCALIDRAW_STATE_PROPERTY,
)
from ea_node_editor.nodes.decorators import in_port, node_type, out_port
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.ui.shell.runtime_clipboard import build_graph_fragment_payload
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge


@node_type(
    type_id="tests.runtime_source",
    display_name="Runtime Source",
    category_path=("Tests",),
    icon="play_arrow",
    ports=(
        out_port("value", data_type='COREX.DataTypes.String'),
        out_port("flow_out", kind="flow"),
    ),
    properties=(),
)
class _RuntimeSourcePlugin:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={"value": "ok"})


@node_type(
    type_id="tests.single_sink",
    display_name="Single Sink",
    category_path=("Tests",),
    icon="input",
    ports=(
        in_port("value", data_type='COREX.DataTypes.String', required=False),
        in_port("flow_in", kind="flow"),
    ),
    properties=(),
)
class _SingleSinkPlugin:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={})


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
)
class _PassiveNotePlugin:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={})


def _build_runtime_registry() -> NodeRegistry:
    registry = NodeRegistry()
    for plugin in (
        _RuntimeSourcePlugin,
        _SingleSinkPlugin,
        _PassiveNotePlugin,
    ):
        registry.register(plugin)
    return registry


def _normalized_runtime_document(document: dict[str, object]) -> dict[str, object]:
    normalized = copy.deepcopy(document)
    for workspace in normalized.get("workspaces", []):
        if not isinstance(workspace, dict):
            continue
        for view in workspace.get("views", []):
            if not isinstance(view, dict):
                continue
            view.pop("hide_optional_ports", None)
        document_fields = workspace.get("document_fields")
        if isinstance(document_fields, dict):
            for view in document_fields.get("views", []):
                if not isinstance(view, dict):
                    continue
                view.pop("hide_optional_ports", None)
        for node in workspace.get("nodes", []):
            if isinstance(node, dict) and node.get("visual_style") == {}:
                node.pop("visual_style")
        for compatibility_key in ("workspace_id", "name", "dirty", "active_view_id", "views"):
            workspace.pop(compatibility_key, None)
    return normalized


class PassiveRuntimeWiringTests(unittest.TestCase):
    def test_dynamic_subnode_ports_surface_data_structure_contract(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        shell = model.add_node(workspace.workspace_id, "core.subnode", "Shell", 0.0, 0.0)
        pin = model.add_node(
            workspace.workspace_id,
            "core.subnode_input",
            "Input",
            0.0,
            0.0,
            properties={"label": "Input", "kind": "data", "data_type": "str"},
        )
        workspace.nodes[pin.node_id].parent_node_id = shell.node_id

        shell_ports = effective_ports(
            node=workspace.nodes[shell.node_id],
            spec=registry.get_spec("core.subnode"),
            workspace_nodes=workspace.nodes,
        )

        self.assertEqual(len(shell_ports), 1)
        self.assertEqual(shell_ports[0].kind, "data")
        self.assertEqual(shell_ports[0].data_access, "item")

    def test_normalization_preserves_ordered_data_fan_in(self) -> None:
        registry = _build_runtime_registry()
        model = GraphModel()
        workspace = model.active_workspace

        source_a = model.add_node(workspace.workspace_id, "tests.runtime_source", "A", 0.0, 0.0)
        source_b = model.add_node(workspace.workspace_id, "tests.runtime_source", "B", 0.0, 120.0)
        sink = model.add_node(workspace.workspace_id, "tests.single_sink", "Sink", 280.0, 0.0)

        model.add_edge(workspace.workspace_id, source_a.node_id, "value", sink.node_id, "value")
        model.add_edge(workspace.workspace_id, source_b.node_id, "value", sink.node_id, "value")

        normalize_project_for_registry(model.project, registry)

        incoming = [
            edge
            for edge in workspace.edges.values()
            if edge.target_node_id == sink.node_id and edge.target_port_key == "value"
        ]

        self.assertEqual(
            [(edge.source_node_id, edge.input_order) for edge in incoming],
            [(source_a.node_id, 0), (source_b.node_id, 1)],
        )

    def test_compile_workspace_document_excludes_passive_nodes_and_flow_edges(self) -> None:
        registry = _build_runtime_registry()
        serializer = JsonProjectSerializer(registry)
        model = GraphModel()
        workspace = model.active_workspace

        source = model.add_node(workspace.workspace_id, "tests.runtime_source", "Source", 0.0, 0.0)
        target = model.add_node(workspace.workspace_id, "tests.single_sink", "Target", 320.0, 0.0)
        passive = model.add_node(workspace.workspace_id, "tests.passive_note", "Note", 160.0, 140.0)

        model.add_edge(workspace.workspace_id, source.node_id, "value", target.node_id, "value")
        model.add_edge(workspace.workspace_id, source.node_id, "flow_out", target.node_id, "flow_in")
        model.add_edge(workspace.workspace_id, source.node_id, "flow_out", passive.node_id, "flow_in")

        workspace_doc = serializer.to_document(model.project)["workspaces"][0]
        with mock.patch.object(
            invariant_kernel,
            "effective_ports",
            wraps=invariant_kernel.effective_ports,
        ) as ports_spy:
            compiled = compile_runtime_workspace(workspace_doc, registry=registry)
        self.assertIsInstance(compiled, RuntimeWorkspace)
        self.assertEqual(ports_spy.call_count, 3)

        self.assertEqual(
            {node.node_id for node in compiled.nodes},
            {source.node_id, target.node_id},
        )
        self.assertEqual(
            [
                (
                    edge.source_node_id,
                    edge.source_port_key,
                    edge.target_node_id,
                    edge.target_port_key,
                    edge.enabled,
                    edge.input_order,
                )
                for edge in compiled.edges
            ],
            [
                (source.node_id, "value", target.node_id, "value", True, 0),
            ],
        )
        self.assertNotIn(passive.node_id, {node.node_id for node in compiled.nodes})
        self.assertEqual(compile_workspace_document(workspace_doc, registry=registry), compiled.to_document())

    def test_folder_explorer_is_excluded_from_runtime_data_edges(self) -> None:
        registry = build_default_registry()
        serializer = JsonProjectSerializer(registry)
        model = GraphModel()
        workspace = model.active_workspace

        folder = model.add_node(
            workspace.workspace_id,
            "io.folder_explorer",
            "Folder Explorer",
            160.0,
            120.0,
            properties={"current_path": r"C:\fixtures"},
        )
        reader = model.add_node(workspace.workspace_id, "io.file_read", "File Read", 360.0, 0.0)

        model.add_edge(workspace.workspace_id, folder.node_id, "current", reader.node_id, "path")

        workspace_doc = serializer.to_document(model.project)["workspaces"][0]
        compiled = compile_runtime_workspace(workspace_doc, registry=registry)

        compiled_node_ids = {node.node_id for node in compiled.nodes}
        self.assertEqual(compiled_node_ids, {reader.node_id})
        self.assertNotIn(folder.node_id, compiled_node_ids)
        self.assertEqual(compiled.edges, ())

    def test_plot_nodes_compile_as_active_runtime_nodes_with_variadic_series_edges(self) -> None:
        registry = build_default_registry()
        serializer = JsonProjectSerializer(registry)
        model = GraphModel()
        workspace = model.active_workspace

        series_a = model.add_node(
            workspace.workspace_id,
            "core.constant",
            "Series A",
            120.0,
            0.0,
            properties={"value": {"label": "A", "values": [1, 2, 3]}},
        )
        series_b = model.add_node(
            workspace.workspace_id,
            "core.constant",
            "Series B",
            120.0,
            140.0,
            properties={"value": {"label": "B", "values": [2, 3, 5]}},
        )
        plot = model.add_node(workspace.workspace_id, "plot.scatter", "Scatter Plot", 340.0, 80.0)

        model.add_edge(workspace.workspace_id, series_a.node_id, "value", plot.node_id, "series")
        model.add_edge(workspace.workspace_id, series_b.node_id, "value", plot.node_id, "series")

        workspace_doc = serializer.to_document(model.project)["workspaces"][0]
        compiled = compile_runtime_workspace(workspace_doc, registry=registry)

        compiled_node_ids = {node.node_id for node in compiled.nodes}
        self.assertEqual(
            compiled_node_ids,
            {series_a.node_id, series_b.node_id, plot.node_id},
        )
        series_edges = [
            edge
            for edge in compiled.edges
            if edge.target_node_id == plot.node_id and edge.target_port_key == "series"
        ]
        self.assertEqual(len(series_edges), 2)
        self.assertEqual(registry.get_spec("plot.scatter").runtime_behavior, "active")

    def test_excalidraw_board_is_excluded_from_runtime_dataflow(self) -> None:
        registry = build_default_registry()
        serializer = JsonProjectSerializer(registry)
        model = GraphModel()
        workspace = model.active_workspace

        source = model.add_node(
            workspace.workspace_id,
            "core.constant",
            "Source",
            0.0,
            0.0,
            properties={"value": "ready"},
        )
        board = model.validated_mutations(workspace.workspace_id, registry).add_node(
            type_id=EXCALIDRAW_BOARD_TYPE_ID,
            title="Excalidraw Board",
            x=160.0,
            y=120.0,
            properties={
                EXCALIDRAW_STATE_PROPERTY: {
                    "type": "excalidraw",
                    "version": 2,
                    "elements": [],
                    "appState": {},
                }
            },
        )
        target = model.add_node(workspace.workspace_id, "core.logger", "Target", 360.0, 0.0)

        model.add_edge(workspace.workspace_id, source.node_id, "as_text", target.node_id, "message")

        workspace_doc = serializer.to_document(model.project)["workspaces"][0]
        compiled = compile_runtime_workspace(workspace_doc, registry=registry)

        self.assertEqual({node.node_id for node in compiled.nodes}, {source.node_id, target.node_id})
        self.assertNotIn(board.node_id, {node.node_id for node in compiled.nodes})
        self.assertEqual(compile_workspace_document(workspace_doc, registry=registry), compiled.to_document())

    def test_build_runtime_snapshot_matches_runtime_document_without_serializer_round_trip_and_compiles_active_workspace(
        self,
    ) -> None:
        registry = _build_runtime_registry()
        serializer = JsonProjectSerializer(registry)
        model = GraphModel()
        workspace = model.active_workspace

        source = model.add_node(workspace.workspace_id, "tests.runtime_source", "Source", 0.0, 0.0)
        target = model.add_node(workspace.workspace_id, "tests.single_sink", "Target", 320.0, 0.0)
        model.add_edge(workspace.workspace_id, source.node_id, "value", target.node_id, "value")
        workspace.nodes[source.node_id].custom_width = 180.0
        workspace.nodes[target.node_id].port_labels["value"] = "Input Value"
        workspace.views[workspace.active_view_id].scope_path = [source.node_id]
        secondary_workspace = model.create_workspace("Secondary")
        model.add_node(secondary_workspace.workspace_id, "tests.passive_note", "Passive", 0.0, 0.0)
        model.set_active_workspace(workspace.workspace_id)
        model.project.metadata["workspace_order"] = [
            secondary_workspace.workspace_id,
            workspace.workspace_id,
        ]
        model.project.metadata["artifact_store"] = {
            "staged": {
                "preview_png": {
                    "absolute_path": "C:/runtime/cache/preview.png",
                }
            }
        }

        with mock.patch(
            "ea_node_editor.persistence.serializer.JsonProjectSerializer",
            side_effect=AssertionError("build_runtime_snapshot should not instantiate JsonProjectSerializer"),
        ):
            runtime_snapshot = build_runtime_snapshot(
                model.project,
                workspace_id=workspace.workspace_id,
                registry=registry,
            )

        self.assertIsInstance(runtime_snapshot, RuntimeSnapshot)
        self.assertEqual(runtime_snapshot.active_workspace_id, workspace.workspace_id)
        self.assertEqual(
            runtime_snapshot.workspace_order,
            (secondary_workspace.workspace_id, workspace.workspace_id),
        )
        normalized_project = copy.deepcopy(model.project)
        normalize_project_for_registry(normalized_project, registry)
        self.assertEqual(
            _normalized_runtime_document(runtime_snapshot.to_document()),
            _normalized_runtime_document(serializer.to_document(normalized_project)),
        )

        compiled = compile_runtime_snapshot(
            runtime_snapshot,
            workspace_id=workspace.workspace_id,
            registry=registry,
        )
        self.assertEqual(
            {node.node_id for node in compiled.nodes},
            {source.node_id, target.node_id},
        )
        self.assertEqual(
            [
                (
                    edge.source_node_id,
                    edge.source_port_key,
                    edge.target_node_id,
                    edge.target_port_key,
                    edge.enabled,
                    edge.input_order,
                )
                for edge in compiled.edges
            ],
            [
                (source.node_id, "value", target.node_id, "value", True, 0),
            ],
        )

    def test_compile_workspace_document_preserves_ordered_fan_in_and_prunes_invalid_ports(self) -> None:
        registry = _build_runtime_registry()
        serializer = JsonProjectSerializer(registry)
        model = GraphModel()
        workspace = model.active_workspace

        source_a = model.add_node(workspace.workspace_id, "tests.runtime_source", "A", 0.0, 0.0)
        source_b = model.add_node(workspace.workspace_id, "tests.runtime_source", "B", 0.0, 120.0)
        sink = model.add_node(workspace.workspace_id, "tests.single_sink", "Sink", 280.0, 0.0)

        model.add_edge(workspace.workspace_id, source_a.node_id, "value", sink.node_id, "value")
        model.add_edge(workspace.workspace_id, source_b.node_id, "value", sink.node_id, "value")
        model.add_edge(workspace.workspace_id, source_a.node_id, "missing", sink.node_id, "value")

        workspace_doc = serializer.to_document(model.project)["workspaces"][0]
        compiled = compile_runtime_workspace(workspace_doc, registry=registry)
        self.assertIsInstance(compiled, RuntimeWorkspace)

        self.assertEqual(
            {node.node_id for node in compiled.nodes},
            {source_a.node_id, source_b.node_id, sink.node_id},
        )
        compiled_edges = [
            (
                edge.source_node_id,
                edge.source_port_key,
                edge.target_node_id,
                edge.target_port_key,
                edge.input_order,
            )
            for edge in compiled.edges
        ]
        self.assertEqual(
            compiled_edges,
            [
                (source_a.node_id, "value", sink.node_id, "value", 0),
                (source_b.node_id, "value", sink.node_id, "value", 1),
            ],
        )

    def test_compile_workspace_document_uses_subnode_contract_without_registry(self) -> None:
        registry = build_default_registry()
        serializer = JsonProjectSerializer(registry)
        model = GraphModel()
        workspace = model.active_workspace

        source = model.add_node(
            workspace.workspace_id,
            "core.constant",
            "Source",
            0.0,
            0.0,
            properties={"value": "C:/fixtures/input.txt"},
        )
        shell = model.add_node(workspace.workspace_id, "core.subnode", "Shell", 260.0, 40.0)
        pin_in = model.add_node(
            workspace.workspace_id,
            "core.subnode_input",
            "Input",
            40.0,
            80.0,
            properties={"label": "In", "kind": "data", "data_type": "str"},
        )
        inner = model.add_node(workspace.workspace_id, "io.file_read", "Inner", 360.0, 100.0)
        pin_out = model.add_node(
            workspace.workspace_id,
            "core.subnode_output",
            "Output",
            520.0,
            80.0,
            properties={"label": "Out", "kind": "data", "data_type": "str"},
        )
        target = model.add_node(workspace.workspace_id, "core.logger", "Target", 760.0, 40.0)

        workspace.nodes[pin_in.node_id].parent_node_id = shell.node_id
        workspace.nodes[inner.node_id].parent_node_id = shell.node_id
        workspace.nodes[pin_out.node_id].parent_node_id = shell.node_id

        model.add_edge(workspace.workspace_id, source.node_id, "as_text", shell.node_id, pin_in.node_id)
        model.add_edge(workspace.workspace_id, pin_in.node_id, "pin", inner.node_id, "path")
        model.add_edge(workspace.workspace_id, inner.node_id, "text", pin_out.node_id, "pin")
        model.add_edge(workspace.workspace_id, shell.node_id, pin_out.node_id, target.node_id, "message")

        workspace_doc = serializer.to_document(model.project)["workspaces"][0]
        compiled = compile_runtime_workspace(workspace_doc, registry=None)
        self.assertIsInstance(compiled, RuntimeWorkspace)

        self.assertEqual(
            {node.node_id for node in compiled.nodes},
            {source.node_id, inner.node_id, target.node_id},
        )
        self.assertCountEqual(
            [
                (
                    edge.source_node_id,
                    edge.source_port_key,
                    edge.target_node_id,
                    edge.target_port_key,
                )
                for edge in compiled.edges
            ],
            [
                (inner.node_id, "text", target.node_id, "message"),
                (source.node_id, "as_text", inner.node_id, "path"),
            ],
        )

    def test_fragment_validation_preserves_data_fan_in(self) -> None:
        registry = _build_runtime_registry()
        model = GraphModel()
        workspace = model.active_workspace
        scene = GraphSceneBridge()
        scene.set_workspace(model, registry, workspace.workspace_id)

        fan_in_fragment = build_graph_fragment_payload(
            nodes=[
                {"ref_id": "src_a", "type_id": "tests.runtime_source", "title": "A", "x": 0.0, "y": 0.0},
                {"ref_id": "src_b", "type_id": "tests.runtime_source", "title": "B", "x": 0.0, "y": 120.0},
                {"ref_id": "sink", "type_id": "tests.single_sink", "title": "Sink", "x": 240.0, "y": 60.0},
            ],
            edges=[
                {
                    "source_ref_id": "src_a",
                    "source_port_key": "value",
                    "target_ref_id": "sink",
                    "target_port_key": "value",
                },
                {
                    "source_ref_id": "src_b",
                    "source_port_key": "value",
                    "target_ref_id": "sink",
                    "target_port_key": "value",
                },
            ],
        )
        self.assertTrue(scene.paste_subgraph_fragment(fan_in_fragment, 120.0, 120.0))
        self.assertEqual(len(workspace.nodes), 3)
        self.assertEqual(len(workspace.edges), 2)


if __name__ == "__main__":
    unittest.main()
