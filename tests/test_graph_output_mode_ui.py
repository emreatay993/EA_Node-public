from __future__ import annotations

import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QUrl
from PyQt6.QtQml import QQmlComponent, QQmlEngine
from PyQt6.QtQuick import QQuickItem
from PyQt6.QtWidgets import QApplication

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.ui_qml.graph_scene_payload import GraphScenePayloadBuilder


class GraphOutputModeUiTests(unittest.TestCase):
    @staticmethod
    def _walk_items(item):
        if isinstance(item, QQuickItem):
            yield item
            for child in item.childItems():
                yield from GraphOutputModeUiTests._walk_items(child)

    @staticmethod
    def _named_item(root, object_name: str, property_key: str | None = None):
        for child in GraphOutputModeUiTests._walk_items(root):
            if child.objectName() != object_name:
                continue
            if property_key is None or str(child.property("propertyKey")) == property_key:
                return child
        raise AssertionError(f"Missing object {object_name!r} propertyKey={property_key!r}")

    def _process_run_output_mode_item(self, output_mode: str) -> dict[str, object]:
        model = GraphModel()
        workspace = model.active_workspace
        model.add_node(
            workspace.workspace_id,
            "io.process_run",
            "Process",
            96.0,
            72.0,
            properties={"output_mode": output_mode},
        )

        builder = GraphScenePayloadBuilder()
        nodes_payload, _backdrops, _minimap_nodes, _edges = builder.rebuild_partitioned_models(
            model=model,
            registry=build_default_registry(),
            workspace_id=workspace.workspace_id,
            scope_path=(),
            graph_theme_bridge=None,
        )
        process_payload = next(
            node_payload for node_payload in nodes_payload if node_payload["type_id"] == "io.process_run"
        )
        return next(
            item for item in process_payload["inline_properties"] if str(item.get("key", "")) == "output_mode"
        )

    def test_graph_scene_payload_builder_routes_node_and_partition_work_through_split_helpers(self) -> None:
        package_dir = (
            Path(__file__).resolve().parents[1]
            / "ea_node_editor"
            / "ui_qml"
            / "graph_scene_payload"
        )
        builder_text = (package_dir / "builder.py").read_text(encoding="utf-8")

        self.assertIn(
            "class _GraphSceneThemeResolver:",
            (package_dir / "theme_inputs.py").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "class _GraphSceneNodePayloadFactory:",
            (package_dir / "factory.py").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "class _GraphSceneBackdropPartitioner:",
            (package_dir / "backdrop_partitioner.py").read_text(encoding="utf-8"),
        )
        current_input_provider = object()
        property_edit_adapters = (object(),)
        keep_width_provider = lambda: True
        with (
            patch(
                "ea_node_editor.ui_qml.graph_scene_payload.builder._GraphSceneNodePayloadFactory",
                autospec=True,
            ) as factory,
            patch(
                "ea_node_editor.ui_qml.graph_scene_payload.builder._GraphSceneBackdropPartitioner",
                autospec=True,
            ) as partitioner,
        ):
            builder = GraphScenePayloadBuilder(
                current_input_provider=current_input_provider,
                property_edit_adapters=property_edit_adapters,
                keep_expanded_node_width_provider=keep_width_provider,
            )
            factory.assert_called_once_with(
                builder.boundary_adapters,
                current_input_provider,
                property_edit_adapters,
                keep_expanded_node_width_provider=keep_width_provider,
            )
            partitioner.assert_called_once_with(factory.return_value)
        self.assertIn("self._backdrop_partitioner.build_payload_models(", builder_text)
        self.assertIn(
            "self._last_mutation_phase_timings_ms = self._backdrop_partitioner.mutation_phase_timings_ms()",
            builder_text,
        )
        self.assertIn("return payloads", builder_text)

    def test_process_run_output_mode_inline_payload_exposes_chip_metadata(self) -> None:
        memory_item = self._process_run_output_mode_item("memory")
        stored_item = self._process_run_output_mode_item("stored")

        self.assertEqual(memory_item["inline_editor"], "enum")
        self.assertEqual(memory_item["enum_values"], ["memory", "stored"])
        self.assertEqual(memory_item["status_chip_text"], "Inline capture")
        self.assertEqual(memory_item["status_chip_variant"], "memory")
        self.assertEqual(memory_item["status_chip_description"], "stdout/stderr stay inline strings")

        self.assertEqual(stored_item["status_chip_text"], "Stored transcripts")
        self.assertEqual(stored_item["status_chip_variant"], "stored")
        self.assertEqual(stored_item["status_chip_description"], "stdout/stderr emit staged artifact refs")

    def test_canvas_options_remove_mode_selector_and_control_settings_section(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        options_text = (
            repo_root
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph_canvas"
            / "GraphCanvasOptionsMenu.qml"
        ).read_text(encoding="utf-8")
        ports_text = (
            repo_root
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph"
            / "GraphNodePortsLayer.qml"
        ).read_text(encoding="utf-8")
        action_router_text = (
            repo_root
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph_canvas"
            / "GraphCanvasActionRouter.qml"
        ).read_text(encoding="utf-8")
        interaction_text = (
            repo_root
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph_canvas"
            / "GraphCanvasInteractionState.qml"
        ).read_text(encoding="utf-8")
        drop_preview_text = (
            repo_root
            / "ea_node_editor"
            / "ui_qml"
            / "components"
            / "graph_canvas"
            / "GraphCanvasDropPreview.qml"
        ).read_text(encoding="utf-8")

        self.assertNotIn('label: "Canvas mode"', options_text)
        for label, value in (
            ("Guided", "guided"),
            ("Mixed", "mixed"),
            ("Advanced", "advanced"),
        ):
            self.assertNotIn(
                f'{{ "label": "{label}", "value": "{value}" }}',
                options_text,
            )
        for retired_snippet in (
            'objectName: "graphNodeSettingsSectionRow"',
            'text: "Settings"',
            'objectName: "graphNodeCompactControlEndpoint"',
            'dispatchNodeAction("toggle_node_settings_section"',
        ):
            self.assertNotIn(retired_snippet, ports_text)
        self.assertNotIn('"toggle_node_settings_section":', action_router_text)
        self.assertIn("port.handle_visible === false", interaction_text)
        self.assertIn(
            "root.sceneBridge.library_drop_preview_payload(payload)",
            interaction_text,
        )
        self.assertIn(
            "GraphNodeSurfaceMetrics.localPortPointForPort(",
            drop_preview_text,
        )

    def test_graph_inline_properties_layer_renders_process_output_mode_chip(self) -> None:
        app = QApplication.instance() or QApplication([])
        engine = QQmlEngine()
        repo_root = Path(__file__).resolve().parents[1]
        probe_qml = textwrap.dedent(
            '''
            import QtQuick 2.15
            import QtQuick.Controls 2.15
            import "ea_node_editor/ui_qml/components/graph" as GraphComponents

            Item {
                id: root
                width: 260
                height: 180

                function buildInlineProperties(mode) {
                    return [
                        {
                            "key": "output_mode",
                            "label": "Output Mode",
                            "inline_editor": "enum",
                            "value": String(mode || "memory"),
                            "enum_values": ["memory", "stored"],
                            "overridden_by_input": false,
                            "input_port_label": "",
                            "status_chip_text": mode === "stored" ? "Stored transcripts" : "Inline capture",
                            "status_chip_variant": mode === "stored" ? "stored" : "memory",
                            "status_chip_description": mode === "stored"
                                ? "stdout/stderr emit staged artifact refs"
                                : "stdout/stderr stay inline strings"
                        }
                    ];
                }

                function setMode(mode) {
                    inlineHost.inlineProperties = buildInlineProperties(mode);
                }

                Item {
                    id: inlineHost
                    objectName: "probeInlineHost"
                    width: 240
                    height: 120
                    property var inlineProperties: root.buildInlineProperties("memory")
                    property var nodeData: ({ "node_id": "node_process_output_mode" })
                    property int inlineBodyHeight: 120
                    property color inlineRowColor: "#24262c"
                    property color inlineRowBorderColor: "#4a4f5a"
                    property color inlineLabelColor: "#d0d5de"
                    property color inlineDrivenTextColor: "#bdc5d3"
                    property color inlineInputBackgroundColor: "#223344"
                    property color inlineInputBorderColor: "#556677"
                    property color inlineInputTextColor: "#ddeeff"
                    property color scopeBadgeColor: "#1D8CE0"
                    property color scopeBadgeBorderColor: "#60CDFF"
                    property color scopeBadgeTextColor: "#f2f4f8"
                    property int nodeTextRenderType: Text.QtRendering
                    property int _inlineRowSpacing: 4
                    property int _inlineRowHeight: 26
                    property var surfaceMetrics: ({
                        "body_left_margin": 8,
                        "body_right_margin": 8,
                        "body_top": 30
                    })

                    signal surfaceControlInteractionStarted(string nodeId)
                    signal inlinePropertyCommitted(string nodeId, string key, var value)

                    function inlineEditorText(modelData) {
                        return String(modelData.value === undefined || modelData.value === null ? "" : modelData.value);
                    }

                    GraphComponents.GraphInlinePropertiesLayer {
                        id: inlineLayer
                        objectName: "probeInlineLayer"
                        anchors.fill: parent
                        host: inlineHost
                    }
                }
            }
            '''
        )

        component = QQmlComponent(engine)
        component.setData(
            probe_qml.encode("utf-8"),
            QUrl.fromLocalFile(str(repo_root) + "/"),
        )
        if component.status() != QQmlComponent.Status.Ready:
            errors = "\n".join(error.toString() for error in component.errors())
            self.fail("Failed to load probe QML:\n" + errors)
        probe = component.create()
        if probe is None:
            errors = "\n".join(error.toString() for error in component.errors())
            self.fail("Failed to instantiate probe QML:\n" + errors)
        app.processEvents()

        chip = self._named_item(probe, "graphNodeInlineStatusChip", "output_mode")
        chip_label = self._named_item(probe, "graphNodeInlineStatusChipLabel", "output_mode")
        self.assertTrue(bool(chip.property("visible")))
        self.assertEqual(chip_label.property("text"), "Inline capture")

        probe.setMode("stored")
        for _index in range(6):
            app.processEvents()

        chip = self._named_item(probe, "graphNodeInlineStatusChip", "output_mode")
        chip_label = self._named_item(probe, "graphNodeInlineStatusChipLabel", "output_mode")
        self.assertTrue(bool(chip.property("visible")))
        self.assertEqual(chip_label.property("text"), "Stored transcripts")


if __name__ == "__main__":
    unittest.main()
