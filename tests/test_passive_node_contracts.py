from __future__ import annotations

import unittest

from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.builtins.passive_annotation import (
    PASSIVE_ANNOTATION_CALLOUT_TYPE_ID,
    PASSIVE_ANNOTATION_GROUP_BACKDROP_TYPE_ID,
    PASSIVE_ANNOTATION_NODE_PLUGINS,
    PASSIVE_ANNOTATION_SECTION_HEADER_TYPE_ID,
    PASSIVE_ANNOTATION_STICKY_NOTE_TYPE_ID,
    PASSIVE_ANNOTATION_TEXT_TYPE_ID,
)
from ea_node_editor.nodes.builtins.passive_flowchart import (
    PASSIVE_FLOWCHART_CALLOUT_TYPE_ID,
    PASSIVE_FLOWCHART_CARD_TYPE_ID,
    PASSIVE_FLOWCHART_CONNECTOR_TYPE_ID,
    PASSIVE_FLOWCHART_DATABASE_TYPE_ID,
    PASSIVE_FLOWCHART_DECISION_TYPE_ID,
    PASSIVE_FLOWCHART_DOCUMENT_TYPE_ID,
    PASSIVE_FLOWCHART_END_TYPE_ID,
    PASSIVE_FLOWCHART_INPUT_OUTPUT_TYPE_ID,
    PASSIVE_FLOWCHART_ISOMETRIC_CUBE_TYPE_ID,
    PASSIVE_FLOWCHART_MESSAGE_TYPE_ID,
    PASSIVE_FLOWCHART_MULTI_DOCUMENT_TYPE_ID,
    PASSIVE_FLOWCHART_NODE_PLUGINS,
    PASSIVE_FLOWCHART_PREDEFINED_PROCESS_TYPE_ID,
    PASSIVE_FLOWCHART_PROCESS_TYPE_ID,
    PASSIVE_FLOWCHART_START_TYPE_ID,
    PASSIVE_FLOWCHART_TICK_TYPE_ID,
    PASSIVE_FLOWCHART_TIMESTAMP_TYPE_ID,
)
from ea_node_editor.nodes.builtins.media_panel import MEDIA_PANEL_TYPE_ID
from ea_node_editor.nodes.builtins.passive_mail import (
    PASSIVE_MAIL_NODE_PLUGINS,
    PASSIVE_MEDIA_MAIL_PANEL_TYPE_ID,
)
from ea_node_editor.nodes.builtins.passive_planning import (
    PASSIVE_PLANNING_DECISION_CARD_TYPE_ID,
    PASSIVE_PLANNING_MILESTONE_CARD_TYPE_ID,
    PASSIVE_PLANNING_NODE_PLUGINS,
    PASSIVE_PLANNING_RISK_CARD_TYPE_ID,
    PASSIVE_PLANNING_TASK_CARD_TYPE_ID,
)
from ea_node_editor.nodes.builtins.web_viewer import (
    WEB_PAGE_VIEWER_NODE_PLUGINS,
    WEB_PAGE_VIEWER_TYPE_ID,
)
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.node_specs import NodeTypeSpec
from ea_node_editor.ui_qml.node_title_icon_sources import title_icon_source_for_node_payload
from ea_node_editor.text_style import RICH_TEXT_SLOT_STYLE_KEYS, rich_text_format_property_key, rich_text_style_property_key

_EXPECTED_CARDINAL_PASSIVE_PORTS = ("top", "right", "bottom", "left")


def _rich_text_extra_keys(content_key: str) -> list[str]:
    return [
        rich_text_format_property_key(content_key),
        *[rich_text_style_property_key(content_key, key) for key in RICH_TEXT_SLOT_STYLE_KEYS],
    ]


def _context() -> ExecutionContext:
    return ExecutionContext(
        run_id="run",
        node_id="node",
        workspace_id="ws",
        inputs={},
        properties={},
        emit_log=lambda _level, _message: None,
    )


def _uses_shape_visual_contract(spec: NodeTypeSpec) -> bool:
    return spec.runtime_behavior == "passive" and spec.surface_family == "flowchart"


class PassiveNodeContractsTests(unittest.TestCase):
    def test_passive_plugins_publish_passive_surface_contracts_and_noop_execution(self) -> None:
        for plugin_cls in (
            *PASSIVE_FLOWCHART_NODE_PLUGINS,
            *PASSIVE_PLANNING_NODE_PLUGINS,
            *PASSIVE_ANNOTATION_NODE_PLUGINS,
            *PASSIVE_MAIL_NODE_PLUGINS,
            *WEB_PAGE_VIEWER_NODE_PLUGINS,
        ):
            plugin = plugin_cls()
            spec = plugin.spec()

            self.assertEqual(spec.runtime_behavior, "passive")
            if str(spec.surface_family) == "group_backdrop":
                self.assertTrue(spec.collapsible)
            else:
                self.assertFalse(spec.collapsible)
            self.assertTrue(spec.surface_family)
            self.assertEqual(plugin.execute(_context()).outputs, {})

    def test_passive_plugins_publish_normalized_render_quality_metadata(self) -> None:
        for plugin_cls in (
            *PASSIVE_FLOWCHART_NODE_PLUGINS,
            *PASSIVE_PLANNING_NODE_PLUGINS,
            *PASSIVE_ANNOTATION_NODE_PLUGINS,
            *PASSIVE_MAIL_NODE_PLUGINS,
            *WEB_PAGE_VIEWER_NODE_PLUGINS,
        ):
            spec = plugin_cls().spec()

            self.assertTrue(spec.render_quality.supported_quality_tiers)
            self.assertIn("full", spec.render_quality.supported_quality_tiers)

    def test_flowchart_passive_nodes_use_flow_only_ports_and_branch_contracts(self) -> None:
        registry = build_default_registry()
        flowchart_type_ids = (
            PASSIVE_FLOWCHART_START_TYPE_ID,
            PASSIVE_FLOWCHART_END_TYPE_ID,
            PASSIVE_FLOWCHART_PROCESS_TYPE_ID,
            PASSIVE_FLOWCHART_DECISION_TYPE_ID,
            PASSIVE_FLOWCHART_DOCUMENT_TYPE_ID,
            PASSIVE_FLOWCHART_CONNECTOR_TYPE_ID,
            PASSIVE_FLOWCHART_INPUT_OUTPUT_TYPE_ID,
            PASSIVE_FLOWCHART_PREDEFINED_PROCESS_TYPE_ID,
            PASSIVE_FLOWCHART_DATABASE_TYPE_ID,
            PASSIVE_FLOWCHART_CARD_TYPE_ID,
            PASSIVE_FLOWCHART_CALLOUT_TYPE_ID,
            PASSIVE_FLOWCHART_MULTI_DOCUMENT_TYPE_ID,
            PASSIVE_FLOWCHART_TICK_TYPE_ID,
            PASSIVE_FLOWCHART_TIMESTAMP_TYPE_ID,
            PASSIVE_FLOWCHART_MESSAGE_TYPE_ID,
            PASSIVE_FLOWCHART_ISOMETRIC_CUBE_TYPE_ID,
        )

        for type_id in flowchart_type_ids:
            spec = registry.get_spec(type_id)
            self.assertEqual(spec.surface_family, "flowchart")
            self.assertTrue(spec.ports)
            expected_property_keys = (
                ["title", "body", "live"]
                if type_id == PASSIVE_FLOWCHART_TIMESTAMP_TYPE_ID
                else [
                    "title",
                    "body",
                    *_rich_text_extra_keys("body"),
                    "body_top",
                    *_rich_text_extra_keys("body_top"),
                    "body_right",
                    *_rich_text_extra_keys("body_right"),
                ]
                if type_id == PASSIVE_FLOWCHART_ISOMETRIC_CUBE_TYPE_ID
                else ["title", "body", *_rich_text_extra_keys("body")]
            )
            self.assertEqual([prop.key for prop in spec.properties], expected_property_keys)
            self.assertEqual(spec.properties[0].type, "str")
            self.assertEqual(spec.properties[0].label, "Title")
            self.assertEqual(spec.properties[1].type, "str")
            self.assertEqual(spec.properties[1].label, "Body")
            self.assertEqual(spec.properties[1].inspector_editor, "textarea")
            if type_id == PASSIVE_FLOWCHART_TIMESTAMP_TYPE_ID:
                self.assertEqual(spec.properties[2].type, "bool")
                self.assertEqual(spec.properties[2].label, "Live")
                self.assertFalse(spec.properties[2].default)
            self.assertTrue(all(port.kind == "flow" and port.data_type == "flow" for port in spec.ports))
            self.assertEqual([port.key for port in spec.ports], ["top", "right", "bottom", "left"])
            self.assertTrue(all(port.direction == "neutral" for port in spec.ports))
            self.assertTrue(all(port.side == port.key for port in spec.ports))
            self.assertTrue(all(port.allow_multiple_connections for port in spec.ports))

        start_spec = registry.get_spec(PASSIVE_FLOWCHART_START_TYPE_ID)
        self.assertEqual([port.key for port in start_spec.ports], ["top", "right", "bottom", "left"])

        end_spec = registry.get_spec(PASSIVE_FLOWCHART_END_TYPE_ID)
        self.assertEqual([port.key for port in end_spec.ports], ["top", "right", "bottom", "left"])
        self.assertTrue(all(port.allow_multiple_connections for port in end_spec.ports))

        decision_spec = registry.get_spec(PASSIVE_FLOWCHART_DECISION_TYPE_ID)
        self.assertEqual([port.key for port in decision_spec.ports], ["top", "right", "bottom", "left"])

    def test_non_flow_passive_nodes_publish_cardinal_neutral_flow_ports(self) -> None:
        registry = build_default_registry()
        passive_type_ids = (
            PASSIVE_PLANNING_TASK_CARD_TYPE_ID,
            PASSIVE_PLANNING_MILESTONE_CARD_TYPE_ID,
            PASSIVE_PLANNING_RISK_CARD_TYPE_ID,
            PASSIVE_PLANNING_DECISION_CARD_TYPE_ID,
            PASSIVE_ANNOTATION_STICKY_NOTE_TYPE_ID,
            PASSIVE_ANNOTATION_CALLOUT_TYPE_ID,
            PASSIVE_ANNOTATION_SECTION_HEADER_TYPE_ID,
            PASSIVE_ANNOTATION_TEXT_TYPE_ID,
            PASSIVE_ANNOTATION_GROUP_BACKDROP_TYPE_ID,
            PASSIVE_MEDIA_MAIL_PANEL_TYPE_ID,
            WEB_PAGE_VIEWER_TYPE_ID,
        )

        for type_id in passive_type_ids:
            spec = registry.get_spec(type_id)
            self.assertEqual([port.key for port in spec.ports], list(_EXPECTED_CARDINAL_PASSIVE_PORTS))
            self.assertTrue(all(port.direction == "neutral" for port in spec.ports))
            self.assertTrue(all(port.kind == "flow" and port.data_type == "flow" for port in spec.ports))
            self.assertTrue(all(port.side == port.key for port in spec.ports))
            self.assertTrue(all(port.allow_multiple_connections for port in spec.ports))

    def test_registry_default_properties_cover_media_and_planning_defaults(self) -> None:
        registry = build_default_registry()

        task_defaults = registry.default_properties(PASSIVE_PLANNING_TASK_CARD_TYPE_ID)
        risk_defaults = registry.default_properties(PASSIVE_PLANNING_RISK_CARD_TYPE_ID)
        media_defaults = registry.default_properties(MEDIA_PANEL_TYPE_ID)
        web_defaults = registry.default_properties(WEB_PAGE_VIEWER_TYPE_ID)
        decision_defaults = registry.default_properties(PASSIVE_FLOWCHART_DECISION_TYPE_ID)
        timestamp_defaults = registry.default_properties(PASSIVE_FLOWCHART_TIMESTAMP_TYPE_ID)
        text_defaults = registry.default_properties(PASSIVE_ANNOTATION_TEXT_TYPE_ID)

        self.assertEqual(task_defaults["title"], "Task")
        self.assertEqual(task_defaults["body_format"], "plain")
        self.assertEqual(task_defaults["body_font_size"], 0)
        self.assertEqual(task_defaults["status"], "todo")
        self.assertEqual(risk_defaults["severity"], "medium")
        self.assertEqual(decision_defaults["title"], "Decision")
        self.assertEqual(decision_defaults["body"], "Decision")
        self.assertEqual(decision_defaults["body_format"], "plain")
        self.assertFalse(timestamp_defaults["live"])
        self.assertEqual(media_defaults["fit_mode"], "contain")
        self.assertFalse(media_defaults["lock_aspect_ratio"])
        self.assertEqual(media_defaults["crop_w"], 1.0)
        self.assertEqual(media_defaults["rotation_degrees"], 0)
        self.assertFalse(media_defaults["mirror_horizontal"])
        self.assertFalse(media_defaults["mirror_vertical"])
        self.assertEqual(media_defaults["page_number"], 1)
        self.assertEqual(web_defaults["start_location"], "")
        self.assertTrue(web_defaults["persist_browser_state"])
        self.assertEqual(web_defaults["browser_state"], {})
        self.assertEqual(text_defaults["text"], "Text")
        self.assertEqual(text_defaults["format"], "markdown")
        self.assertEqual(text_defaults["font_family"], "Caveat")
        self.assertEqual(text_defaults["font_size"], 18)
        self.assertEqual(text_defaults["font_weight"], "normal")
        self.assertEqual(text_defaults["text_color"], "")
        self.assertEqual(text_defaults["horizontal_alignment"], "center")
        self.assertEqual(text_defaults["wrap_mode"], "word")

    def test_bare_text_annotation_publishes_text_properties_and_color_editors(self) -> None:
        spec = build_default_registry().get_spec(PASSIVE_ANNOTATION_TEXT_TYPE_ID)
        properties = {prop.key: prop for prop in spec.properties}

        self.assertEqual(spec.display_name, "Text")
        self.assertEqual(spec.category, "Annotation")
        self.assertEqual(spec.surface_family, "annotation")
        self.assertEqual(spec.surface_variant, "text")
        self.assertEqual([port.key for port in spec.ports], list(_EXPECTED_CARDINAL_PASSIVE_PORTS))
        self.assertEqual(properties["text"].inspector_editor, "textarea")
        self.assertEqual(properties["format"].enum_values, ("markdown", "plain"))
        self.assertEqual(properties["font_family"].inspector_editor, "font_family")
        self.assertEqual(properties["font_weight"].enum_values, ("normal", "medium", "demibold", "bold", "black"))
        self.assertEqual(properties["text_color"].inspector_editor, "color")
        self.assertEqual(properties["text_color"].inline_editor, "color")
        self.assertEqual(properties["background_color"].inspector_editor, "color")
        self.assertEqual(properties["background_color"].inline_editor, "color")

    def test_prose_passive_nodes_publish_rich_text_slot_contracts(self) -> None:
        registry = build_default_registry()

        for type_id, content_key in (
            (PASSIVE_ANNOTATION_STICKY_NOTE_TYPE_ID, "body"),
            (PASSIVE_ANNOTATION_CALLOUT_TYPE_ID, "body"),
            (PASSIVE_ANNOTATION_SECTION_HEADER_TYPE_ID, "subtitle"),
            (PASSIVE_PLANNING_TASK_CARD_TYPE_ID, "body"),
            (PASSIVE_PLANNING_MILESTONE_CARD_TYPE_ID, "body"),
            (PASSIVE_PLANNING_RISK_CARD_TYPE_ID, "body"),
            (PASSIVE_PLANNING_DECISION_CARD_TYPE_ID, "body"),
            (PASSIVE_FLOWCHART_PROCESS_TYPE_ID, "body"),
        ):
            properties = {prop.key: prop for prop in registry.get_spec(type_id).properties}
            self.assertEqual(properties[rich_text_format_property_key(content_key)].default, "plain")
            self.assertEqual(properties[rich_text_style_property_key(content_key, "font_size")].default, 0)
            self.assertFalse(properties[rich_text_format_property_key(content_key)].inspector_visible)
            self.assertFalse(properties[rich_text_style_property_key(content_key, "font_size")].inspector_visible)

        timestamp_properties = {prop.key for prop in registry.get_spec(PASSIVE_FLOWCHART_TIMESTAMP_TYPE_ID).properties}
        self.assertNotIn("body_format", timestamp_properties)

    def test_title_icon_passive_plugins_remain_ineligible(self) -> None:
        for plugin_cls in (
            *PASSIVE_FLOWCHART_NODE_PLUGINS,
            *PASSIVE_PLANNING_NODE_PLUGINS,
            *PASSIVE_ANNOTATION_NODE_PLUGINS,
            *PASSIVE_MAIL_NODE_PLUGINS,
            *WEB_PAGE_VIEWER_NODE_PLUGINS,
        ):
            spec = plugin_cls().spec()
            self.assertEqual(spec.runtime_behavior, "passive")
            if _uses_shape_visual_contract(spec):
                self.assertEqual(spec.icon, "")
            else:
                self.assertTrue(spec.icon)
            self.assertEqual(title_icon_source_for_node_payload(spec), "")


if __name__ == "__main__":
    unittest.main()
