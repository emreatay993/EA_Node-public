from __future__ import annotations

import unittest

from ea_node_editor.graph.effective_ports import effective_ports
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.builtins.passive_flowchart import PASSIVE_FLOWCHART_TIMESTAMP_BODY_PLACEHOLDER
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.text_style import RICH_TEXT_SLOT_STYLE_KEYS, rich_text_format_property_key, rich_text_style_property_key
from ea_node_editor.ui_qml.node_title_icon_sources import title_icon_source_for_node_payload

_EXPECTED_CARDINAL_PORTS = (
    ("top", "neutral", True, "top"),
    ("right", "neutral", True, "right"),
    ("bottom", "neutral", True, "bottom"),
    ("left", "neutral", True, "left"),
)


def _rich_text_extra_keys(content_key: str) -> tuple[str, ...]:
    return (
        rich_text_format_property_key(content_key),
        *(rich_text_style_property_key(content_key, key) for key in RICH_TEXT_SLOT_STYLE_KEYS),
    )

_EXPECTED_FLOWCHART_SPECS = {
    "passive.flowchart.start": {
        "display_name": "Start",
        "surface_variant": "start",
        "ports": _EXPECTED_CARDINAL_PORTS,
        "properties": ("title", "body", *_rich_text_extra_keys("body")),
    },
    "passive.flowchart.end": {
        "display_name": "End",
        "surface_variant": "end",
        "ports": _EXPECTED_CARDINAL_PORTS,
        "properties": ("title", "body", *_rich_text_extra_keys("body")),
    },
    "passive.flowchart.process": {
        "display_name": "Process",
        "surface_variant": "process",
        "ports": _EXPECTED_CARDINAL_PORTS,
        "properties": ("title", "body", *_rich_text_extra_keys("body")),
    },
    "passive.flowchart.decision": {
        "display_name": "Decision",
        "surface_variant": "decision",
        "ports": _EXPECTED_CARDINAL_PORTS,
        "properties": ("title", "body", *_rich_text_extra_keys("body")),
    },
    "passive.flowchart.document": {
        "display_name": "Document",
        "surface_variant": "document",
        "ports": _EXPECTED_CARDINAL_PORTS,
        "properties": ("title", "body", *_rich_text_extra_keys("body")),
    },
    "passive.flowchart.connector": {
        "display_name": "Connector",
        "surface_variant": "connector",
        "ports": _EXPECTED_CARDINAL_PORTS,
        "properties": ("title", "body", *_rich_text_extra_keys("body")),
    },
    "passive.flowchart.input_output": {
        "display_name": "Input / Output",
        "surface_variant": "input_output",
        "ports": _EXPECTED_CARDINAL_PORTS,
        "properties": ("title", "body", *_rich_text_extra_keys("body")),
    },
    "passive.flowchart.predefined_process": {
        "display_name": "Predefined Process",
        "surface_variant": "predefined_process",
        "ports": _EXPECTED_CARDINAL_PORTS,
        "properties": ("title", "body", *_rich_text_extra_keys("body")),
    },
    "passive.flowchart.database": {
        "display_name": "Database",
        "surface_variant": "database",
        "ports": _EXPECTED_CARDINAL_PORTS,
        "properties": ("title", "body", *_rich_text_extra_keys("body")),
    },
    "passive.flowchart.card": {
        "display_name": "Card",
        "surface_variant": "card",
        "ports": _EXPECTED_CARDINAL_PORTS,
        "properties": ("title", "body", *_rich_text_extra_keys("body")),
        "body_default": "",
    },
    "passive.flowchart.callout": {
        "display_name": "Callout",
        "surface_variant": "callout",
        "ports": _EXPECTED_CARDINAL_PORTS,
        "properties": ("title", "body", *_rich_text_extra_keys("body")),
        "body_default": "",
    },
    "passive.flowchart.multi_document": {
        "display_name": "Multi-Document",
        "surface_variant": "multi_document",
        "ports": _EXPECTED_CARDINAL_PORTS,
        "properties": ("title", "body", *_rich_text_extra_keys("body")),
        "body_default": "",
    },
    "passive.flowchart.tick": {
        "display_name": "Tick",
        "surface_variant": "tick",
        "ports": _EXPECTED_CARDINAL_PORTS,
        "properties": ("title", "body", *_rich_text_extra_keys("body")),
        "body_default": "",
    },
    "passive.flowchart.timestamp": {
        "display_name": "Timestamp",
        "surface_variant": "timestamp",
        "ports": _EXPECTED_CARDINAL_PORTS,
        "properties": ("title", "body", "live"),
        "body_default": PASSIVE_FLOWCHART_TIMESTAMP_BODY_PLACEHOLDER,
        "live_default": False,
    },
    "passive.flowchart.message": {
        "display_name": "Message",
        "surface_variant": "message",
        "ports": _EXPECTED_CARDINAL_PORTS,
        "properties": ("title", "body", *_rich_text_extra_keys("body")),
        "body_default": "",
    },
    "passive.flowchart.isometric_cube": {
        "display_name": "Isometric Cube",
        "surface_variant": "isometric_cube",
        "ports": _EXPECTED_CARDINAL_PORTS,
        "properties": (
            "title",
            "body",
            *_rich_text_extra_keys("body"),
            "body_top",
            *_rich_text_extra_keys("body_top"),
            "body_right",
            *_rich_text_extra_keys("body_right"),
        ),
        "body_default": "",
    },
    "passive.flowchart.cube": {
        "display_name": "Cube",
        "surface_variant": "cube",
        "ports": _EXPECTED_CARDINAL_PORTS,
        "properties": ("title", "body", *_rich_text_extra_keys("body")),
        "body_default": "",
    },
    "passive.flowchart.actor": {
        "display_name": "Actor",
        "surface_variant": "actor",
        "ports": _EXPECTED_CARDINAL_PORTS,
        "properties": ("title", "body", *_rich_text_extra_keys("body")),
        "body_default": "",
    },
    "passive.flowchart.star": {
        "display_name": "Star",
        "surface_variant": "star",
        "ports": _EXPECTED_CARDINAL_PORTS,
        "properties": ("title", "body", *_rich_text_extra_keys("body")),
        "body_default": "",
    },
    "passive.flowchart.x": {
        "display_name": "X",
        "surface_variant": "x",
        "ports": _EXPECTED_CARDINAL_PORTS,
        "properties": ("title", "body", *_rich_text_extra_keys("body")),
        "body_default": "",
    },
}


class PassiveFlowchartCatalogTests(unittest.TestCase):
    def test_locked_flowchart_type_ids_remain_stable(self) -> None:
        registry = build_default_registry()

        self.assertEqual(
            set(_EXPECTED_FLOWCHART_SPECS),
            {
                "passive.flowchart.start",
                "passive.flowchart.end",
                "passive.flowchart.process",
                "passive.flowchart.decision",
                "passive.flowchart.document",
                "passive.flowchart.connector",
                "passive.flowchart.input_output",
                "passive.flowchart.predefined_process",
                "passive.flowchart.database",
                "passive.flowchart.card",
                "passive.flowchart.callout",
                "passive.flowchart.multi_document",
                "passive.flowchart.tick",
                "passive.flowchart.timestamp",
                "passive.flowchart.message",
                "passive.flowchart.isometric_cube",
                "passive.flowchart.cube",
                "passive.flowchart.actor",
                "passive.flowchart.star",
                "passive.flowchart.x",
            },
        )
        for type_id in _EXPECTED_FLOWCHART_SPECS:
            self.assertIsNotNone(registry.get_spec(type_id))

    def test_default_registry_registers_locked_flowchart_catalog_specs(self) -> None:
        registry = build_default_registry()

        for type_id, expected in _EXPECTED_FLOWCHART_SPECS.items():
            spec = registry.get_spec(type_id)

            self.assertEqual(spec.display_name, expected["display_name"])
            self.assertEqual(spec.category, "Flowchart")
            self.assertEqual(spec.runtime_behavior, "passive")
            self.assertEqual(spec.surface_family, "flowchart")
            self.assertEqual(spec.surface_variant, expected["surface_variant"])
            self.assertFalse(spec.collapsible)
            self.assertEqual(
                tuple(
                    (port.key, port.direction, port.allow_multiple_connections, port.side)
                    for port in spec.ports
                ),
                expected["ports"],
            )
            self.assertEqual(tuple(prop.key for prop in spec.properties), expected["properties"])
            self.assertEqual(spec.properties[0].default, expected["display_name"])
            self.assertEqual(
                spec.properties[1].default,
                expected.get("body_default", expected["display_name"]),
            )
            self.assertEqual(spec.properties[1].inspector_editor, "textarea")
            if "live_default" in expected:
                self.assertEqual(spec.properties[2].type, "bool")
                self.assertEqual(spec.properties[2].label, "Live")
                self.assertEqual(spec.properties[2].default, expected["live_default"])
            self.assertTrue(all(port.kind == "flow" for port in spec.ports))
            self.assertTrue(all(port.data_type == "flow" for port in spec.ports))

    def test_effective_flowchart_ports_publish_cardinal_side_metadata(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(
            workspace.workspace_id,
            "passive.flowchart.decision",
            "Decision",
            40.0,
            60.0,
        )
        spec = registry.get_spec("passive.flowchart.decision")
        ports = effective_ports(node=node, spec=spec, workspace_nodes=workspace.nodes)

        self.assertEqual(
            tuple((port.key, port.direction, port.side) for port in ports),
            (
                ("top", "neutral", "top"),
                ("right", "neutral", "right"),
                ("bottom", "neutral", "bottom"),
                ("left", "neutral", "left"),
            ),
        )

    def test_flowchart_decision_ports_are_cardinal_and_edge_label_driven(self) -> None:
        registry = build_default_registry()
        spec = registry.get_spec("passive.flowchart.decision")

        self.assertEqual(
            [port.key for port in spec.ports],
            ["top", "right", "bottom", "left"],
        )
        self.assertFalse(any(port.key in {"branch_a", "branch_b"} for port in spec.ports))
        self.assertFalse(any(port.key.lower() in {"yes", "no"} for port in spec.ports))

    def test_flowchart_specs_do_not_publish_parallel_icon_metadata(self) -> None:
        registry = build_default_registry()

        for type_id in _EXPECTED_FLOWCHART_SPECS:
            spec = registry.get_spec(type_id)
            self.assertEqual(spec.icon, "")
            self.assertEqual(title_icon_source_for_node_payload(spec), "")


if __name__ == "__main__":
    unittest.main()
