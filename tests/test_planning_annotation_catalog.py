from __future__ import annotations

import unittest

from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.text_style import RICH_TEXT_SLOT_STYLE_KEYS, rich_text_format_property_key, rich_text_style_property_key
from ea_node_editor.ui_qml.edge_routing import port_scene_pos
from ea_node_editor.ui_qml.graph_surface_metrics import node_surface_metrics

def _rich_text_extra_keys(content_key: str) -> tuple[str, ...]:
    return (
        rich_text_format_property_key(content_key),
        *(rich_text_style_property_key(content_key, key) for key in RICH_TEXT_SLOT_STYLE_KEYS),
    )

_EXPECTED_PLANNING_SPECS = {
    "passive.planning.task_card": {
        "display_name": "Task Card",
        "surface_variant": "task_card",
        "properties": ("title", "body", *_rich_text_extra_keys("body"), "owner", "due_date", "status"),
        "enum_property": ("status", ("todo", "in_progress", "blocked", "done")),
    },
    "passive.planning.milestone_card": {
        "display_name": "Milestone Card",
        "surface_variant": "milestone_card",
        "properties": ("title", "body", *_rich_text_extra_keys("body"), "target_date", "status"),
        "enum_property": ("status", ("planned", "at_risk", "done")),
    },
    "passive.planning.risk_card": {
        "display_name": "Risk Card",
        "surface_variant": "risk_card",
        "properties": ("title", "body", *_rich_text_extra_keys("body"), "severity", "mitigation"),
        "enum_property": ("severity", ("low", "medium", "high", "critical")),
    },
    "passive.planning.decision_card": {
        "display_name": "Decision Card",
        "surface_variant": "decision_card",
        "properties": ("title", "body", *_rich_text_extra_keys("body"), "state", "outcome"),
        "enum_property": ("state", ("open", "decided", "deferred")),
    },
}

_EXPECTED_ANNOTATION_SPECS = {
    "passive.annotation.sticky_note": {
        "display_name": "Sticky Note",
        "surface_variant": "sticky_note",
        "properties": ("title", "body", *_rich_text_extra_keys("body")),
    },
    "passive.annotation.callout": {
        "display_name": "Callout",
        "surface_variant": "callout",
        "properties": ("title", "body", *_rich_text_extra_keys("body")),
    },
    "passive.annotation.section_header": {
        "display_name": "Section Header",
        "surface_variant": "section_header",
        "properties": ("title", "subtitle", *_rich_text_extra_keys("subtitle")),
    },
    "passive.annotation.text": {
        "display_name": "Text",
        "surface_variant": "text",
        "properties": (
            "text",
            "format",
            "font_family",
            "font_size",
            "font_weight",
            "italic",
            "underline",
            "strikeout",
            "text_color",
            "background_color",
            "horizontal_alignment",
            "vertical_alignment",
            "wrap_mode",
            "line_height",
            "letter_spacing",
            "padding",
            "opacity",
        ),
    },
}

_EXPECTED_CARDINAL_PORTS = (
    ("top", "neutral", True, "top"),
    ("right", "neutral", True, "right"),
    ("bottom", "neutral", True, "bottom"),
    ("left", "neutral", True, "left"),
)


class PlanningAnnotationCatalogTests(unittest.TestCase):
    def test_default_registry_registers_locked_planning_catalog_specs(self) -> None:
        registry = build_default_registry()

        for type_id, expected in _EXPECTED_PLANNING_SPECS.items():
            spec = registry.get_spec(type_id)

            self.assertEqual(spec.display_name, expected["display_name"])
            self.assertEqual(spec.category, "Planning")
            self.assertEqual(spec.runtime_behavior, "passive")
            self.assertEqual(spec.surface_family, "planning")
            self.assertEqual(spec.surface_variant, expected["surface_variant"])
            self.assertFalse(spec.collapsible)
            self.assertEqual(
                tuple((port.key, port.direction, port.allow_multiple_connections, port.side) for port in spec.ports),
                _EXPECTED_CARDINAL_PORTS,
            )
            self.assertEqual(tuple(prop.key for prop in spec.properties), expected["properties"])
            if type_id == "passive.annotation.text":
                font_family_spec = next(prop for prop in spec.properties if prop.key == "font_family")
                self.assertEqual(font_family_spec.inspector_editor, "font_family")
            if type_id == "passive.annotation.text":
                defaults = {prop.key: prop.default for prop in spec.properties}
                self.assertEqual(defaults["horizontal_alignment"], "center")
                self.assertEqual(defaults["vertical_alignment"], "middle")
            enum_key, enum_values = expected["enum_property"]
            enum_spec = next(prop for prop in spec.properties if prop.key == enum_key)
            self.assertEqual(enum_spec.enum_values, enum_values)

    def test_planning_and_annotation_use_rectangular_cardinal_anchor_points(self) -> None:
        registry = build_default_registry()

        for type_id in (
            "passive.planning.task_card",
            "passive.annotation.sticky_note",
        ):
            spec = registry.get_spec(type_id)
            node = NodeInstance(
                node_id=f"node_{type_id.rsplit('.', 1)[-1]}",
                type_id=type_id,
                title=spec.display_name,
                x=40.0,
                y=30.0,
            )
            metrics = node_surface_metrics(node, spec, {node.node_id: node})
            width = metrics.default_width
            height = metrics.default_height

            top = port_scene_pos(node, spec, "top", {node.node_id: node})
            right = port_scene_pos(node, spec, "right", {node.node_id: node})
            bottom = port_scene_pos(node, spec, "bottom", {node.node_id: node})
            left = port_scene_pos(node, spec, "left", {node.node_id: node})

            self.assertAlmostEqual(top.x() - node.x, width * 0.5, places=4)
            self.assertAlmostEqual(top.y() - node.y, 0.5, places=4)
            self.assertAlmostEqual(right.x() - node.x, width - 0.5, places=4)
            self.assertAlmostEqual(right.y() - node.y, height * 0.5, places=4)
            self.assertAlmostEqual(bottom.x() - node.x, width * 0.5, places=4)
            self.assertAlmostEqual(bottom.y() - node.y, height - 0.5, places=4)
            self.assertAlmostEqual(left.x() - node.x, 0.5, places=4)
            self.assertAlmostEqual(left.y() - node.y, height * 0.5, places=4)

    def test_default_registry_registers_locked_annotation_catalog_specs(self) -> None:
        registry = build_default_registry()

        for type_id, expected in _EXPECTED_ANNOTATION_SPECS.items():
            spec = registry.get_spec(type_id)

            self.assertEqual(spec.display_name, expected["display_name"])
            self.assertEqual(spec.category, "Annotation")
            self.assertEqual(spec.runtime_behavior, "passive")
            self.assertEqual(spec.surface_family, "annotation")
            self.assertEqual(spec.surface_variant, expected["surface_variant"])
            self.assertFalse(spec.collapsible)
            self.assertEqual(
                tuple((port.key, port.direction, port.allow_multiple_connections, port.side) for port in spec.ports),
                _EXPECTED_CARDINAL_PORTS,
            )
            self.assertEqual(tuple(prop.key for prop in spec.properties), expected["properties"])




if __name__ == "__main__":
    unittest.main()
