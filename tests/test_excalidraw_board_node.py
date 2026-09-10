from __future__ import annotations

import unittest

from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.builtins.excalidraw import (
    EXCALIDRAW_BOARD_SURFACE_FAMILY,
    EXCALIDRAW_BOARD_SURFACE_VARIANT,
    EXCALIDRAW_BOARD_TYPE_ID,
    EXCALIDRAW_CATEGORY,
    EXCALIDRAW_NODE_PLUGINS,
    EXCALIDRAW_PREVIEW_REF_PROPERTY,
    EXCALIDRAW_STATE_PROPERTY,
)
from ea_node_editor.nodes.node_specs import property_visible_in_inspector
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.nodes.execution_context import ExecutionContext


class ExcalidrawBoardNodeTests(unittest.TestCase):
    _EXPECTED_CARDINAL_PORTS = (
        ("top", "neutral", "flow", "flow", True, "top"),
        ("right", "neutral", "flow", "flow", True, "right"),
        ("bottom", "neutral", "flow", "flow", True, "bottom"),
        ("left", "neutral", "flow", "flow", True, "left"),
    )

    def test_default_registry_registers_excalidraw_board_contract(self) -> None:
        registry = build_default_registry()
        spec = registry.get_spec(EXCALIDRAW_BOARD_TYPE_ID)

        self.assertEqual(spec.type_id, EXCALIDRAW_BOARD_TYPE_ID)
        self.assertEqual(spec.display_name, "Excalidraw Board")
        self.assertEqual(spec.category, EXCALIDRAW_CATEGORY)
        self.assertEqual(spec.runtime_behavior, "passive")
        self.assertEqual(spec.surface_family, EXCALIDRAW_BOARD_SURFACE_FAMILY)
        self.assertEqual(spec.surface_variant, EXCALIDRAW_BOARD_SURFACE_VARIANT)
        self.assertFalse(spec.collapsible)
        self.assertEqual(
            tuple(
                (
                    port.key,
                    port.direction,
                    port.kind,
                    port.data_type,
                    port.allow_multiple_connections,
                    port.side,
                )
                for port in spec.ports
            ),
            self._EXPECTED_CARDINAL_PORTS,
        )
        self.assertEqual(
            tuple(prop.key for prop in spec.properties),
            (EXCALIDRAW_STATE_PROPERTY, EXCALIDRAW_PREVIEW_REF_PROPERTY),
        )

    def test_registry_validation_accepts_corex_web_surface_family(self) -> None:
        registry = NodeRegistry()

        for plugin_cls in EXCALIDRAW_NODE_PLUGINS:
            registry.register(plugin_cls)

        self.assertEqual(
            registry.get_spec(EXCALIDRAW_BOARD_TYPE_ID).surface_family,
            EXCALIDRAW_BOARD_SURFACE_FAMILY,
        )

    def test_excalidraw_board_property_defaults_and_preview_ref_contract(self) -> None:
        registry = build_default_registry()
        defaults = registry.default_properties(EXCALIDRAW_BOARD_TYPE_ID)

        self.assertEqual(
            defaults,
            {
                EXCALIDRAW_STATE_PROPERTY: {},
                EXCALIDRAW_PREVIEW_REF_PROPERTY: "",
            },
        )

        defaults[EXCALIDRAW_STATE_PROPERTY]["elements"] = [{"id": "mutated"}]
        self.assertEqual(registry.default_properties(EXCALIDRAW_BOARD_TYPE_ID)[EXCALIDRAW_STATE_PROPERTY], {})

        preview_ref = {
            "artifact_ref": "saved://excalidraw_board_preview",
            "mime_type": "image/png",
        }
        normalized = registry.normalize_properties(
            EXCALIDRAW_BOARD_TYPE_ID,
            {
                EXCALIDRAW_STATE_PROPERTY: {"elements": [], "appState": {}},
                EXCALIDRAW_PREVIEW_REF_PROPERTY: preview_ref,
            },
            include_defaults=True,
        )

        self.assertEqual(normalized[EXCALIDRAW_PREVIEW_REF_PROPERTY], preview_ref)
        self.assertNotIn("data", normalized[EXCALIDRAW_PREVIEW_REF_PROPERTY])
        self.assertNotIn("base64", normalized[EXCALIDRAW_PREVIEW_REF_PROPERTY])

    def test_excalidraw_state_and_preview_ref_are_hidden_from_normal_inspector(self) -> None:
        spec = build_default_registry().get_spec(EXCALIDRAW_BOARD_TYPE_ID)
        properties = {prop.key: prop for prop in spec.properties}

        state_property = properties[EXCALIDRAW_STATE_PROPERTY]
        preview_ref_property = properties[EXCALIDRAW_PREVIEW_REF_PROPERTY]

        self.assertEqual(state_property.type, "json")
        self.assertEqual(state_property.default, {})
        self.assertFalse(property_visible_in_inspector(state_property))
        self.assertEqual(preview_ref_property.type, "json")
        self.assertFalse(property_visible_in_inspector(preview_ref_property))

    def test_excalidraw_board_plugin_is_noop_passive_execution(self) -> None:
        ctx = ExecutionContext(
            run_id="run",
            node_id="node",
            workspace_id="ws",
            inputs={},
            properties={},
            emit_log=lambda _level, _message: None,
        )

        self.assertEqual(EXCALIDRAW_NODE_PLUGINS[0]().execute(ctx).outputs, {})


if __name__ == "__main__":
    unittest.main()
