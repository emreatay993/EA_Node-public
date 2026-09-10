from __future__ import annotations

import unittest

from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.instance_resolution import resolve_instance_ports
from ea_node_editor.nodes.node_specs import (
    DynamicPortGroupSpec,
    NodeTypeSpec,
    PortSpec,
    PropertySpec,
)
from ea_node_editor.nodes.registry import NodeRegistry
from tests.test_registry_validation import (
    _Plugin,
    _dynamic_input_ports,
    _dynamic_key_factory,
    _dynamic_output_ports,
    _factory,
)


class PropertyNormalizationTests(unittest.TestCase):
    def test_default_properties_are_deep_copied_per_instance(self) -> None:
        registry = NodeRegistry()
        spec = NodeTypeSpec(
            type_id="tests.deep_copy",
            display_name="Deep Copy",
            category_path=("Tests",),
            icon="",
            ports=(PortSpec("value", "out", "data", "COREX.DataTypes.Any"),),
            properties=(PropertySpec("payload", "json", {"items": []}, "Payload"),),
        )
        registry.register(_factory(spec))

        first = registry.default_properties("tests.deep_copy")
        second = registry.default_properties("tests.deep_copy")
        first["payload"]["items"].append("x")

        self.assertEqual(second["payload"], {"items": []})

    def test_dynamic_ports_resolve_in_declared_order_and_normalize_backing_properties(
        self,
    ) -> None:
        registry = NodeRegistry()
        output_group = DynamicPortGroupSpec(
            "outputs",
            "port_ids",
            "out",
            _dynamic_output_ports,
            _dynamic_key_factory,
            minimum=1,
            maximum=3,
            rename_mode="label",
        )
        input_group = DynamicPortGroupSpec(
            "inputs",
            "input_ids",
            "in",
            _dynamic_input_ports,
            _dynamic_key_factory,
        )
        spec = NodeTypeSpec(
            type_id="tests.dynamic_ports",
            display_name="Dynamic Ports",
            category_path=("Tests",),
            icon="",
            ports=(PortSpec("static", "out", "data", "COREX.DataTypes.String"),),
            properties=(
                PropertySpec(
                    "port_ids", "json", ["alpha"], "Port ids", inspector_visible=False
                ),
                PropertySpec(
                    "input_ids",
                    "json",
                    ["payload"],
                    "Input ids",
                    inspector_visible=False,
                ),
                PropertySpec("port_limit", "int", 99, "Port limit"),
            ),
            dynamic_port_groups=(output_group, input_group),
        )
        factory_calls = 0

        def factory() -> _Plugin:
            nonlocal factory_calls
            factory_calls += 1
            return _Plugin(spec)

        registry.register_descriptor(spec, factory)

        self.assertEqual(
            [port.key for port in resolve_instance_ports(spec, {})],
            ["static", "alpha", "payload"],
        )
        self.assertEqual(
            [
                port.key
                for port in resolve_instance_ports(
                    spec,
                    {"port_ids": ["first", "second"], "port_limit": "1"},
                )
            ],
            ["static", "first", "payload"],
        )
        self.assertEqual(
            registry.default_properties(spec.type_id)["port_ids"], ["alpha"]
        )
        self.assertEqual(
            registry.normalize_properties(
                spec.type_id,
                {"port_ids": ["beta", "gamma"]},
                include_defaults=False,
            ),
            {"port_ids": ["beta", "gamma"]},
        )
        self.assertEqual(
            registry.normalize_properties(
                spec.type_id,
                {"port_ids": [1]},
                include_defaults=False,
            ),
            {"port_ids": ["1"]},
        )
        self.assertEqual(
            registry.normalize_properties(spec.type_id, {}, include_defaults=False),
            {},
        )
        with self.assertRaisesRegex(ValueError, "allows at most 3 ports"):
            registry.normalize_properties(
                spec.type_id,
                {"port_ids": ["a", "b", "c", "d"]},
                include_defaults=False,
            )
        self.assertEqual(factory_calls, 0)

    def test_normalize_property_value_and_properties_fall_back_to_defaults(
        self,
    ) -> None:
        registry = NodeRegistry()
        spec = NodeTypeSpec(
            type_id="tests.normalize",
            display_name="Normalize",
            category_path=("Tests",),
            icon="",
            ports=(PortSpec("value", "out", "data", "COREX.DataTypes.Any"),),
            properties=(
                PropertySpec("count", "int", 7, "Count"),
                PropertySpec("enabled", "bool", False, "Enabled"),
            ),
        )
        registry.register(_factory(spec))

        self.assertEqual(
            registry.normalize_property_value("tests.normalize", "count", "15"), 15
        )
        self.assertEqual(
            registry.normalize_property_value("tests.normalize", "count", "bad"), 7
        )
        self.assertFalse(
            registry.normalize_property_value("tests.normalize", "enabled", "true")
        )

        self.assertEqual(
            registry.normalize_properties(
                "tests.normalize", {"count": "15"}, include_defaults=False
            ),
            {"count": 15},
        )
        self.assertEqual(
            registry.normalize_properties(
                "tests.normalize", {"count": "15"}, include_defaults=True
            ),
            {"count": 15, "enabled": False},
        )

    def test_select_slider_and_web_browser_state_use_exact_builtin_policy(self) -> None:
        registry = build_default_registry(include_public_plugins=False)

        self.assertEqual(
            registry.normalize_properties(
                "data.select",
                {
                    "options": [
                        {"name": "One", "value": "1"},
                        {"name": "Two", "value": "2"},
                    ],
                    "selected_index": 9,
                },
            ),
            {
                "options": [
                    {"name": "One", "value": "1"},
                    {"name": "Two", "value": "2"},
                ],
                "selected_index": 1,
            },
        )
        self.assertEqual(
            registry.normalize_properties(
                "data.number_slider",
                {
                    "value": 25.0,
                    "minimum": 10.0,
                    "maximum": 0.0,
                    "rounding": "integer",
                    "decimals": 99,
                },
            ),
            {
                "value": 11.0,
                "minimum": 10.0,
                "maximum": 11.0,
                "rounding": "integer",
                "decimals": 6,
            },
        )
        self.assertEqual(
            registry.normalize_properties(
                "web.page_viewer",
                {
                    "persist_browser_state": False,
                    "browser_state": {"current_url": "https://example.com"},
                },
                include_defaults=False,
            ),
            {
                "persist_browser_state": False,
                "browser_state": {},
                "display_mode": "fit_width",
            },
        )
        self.assertEqual(
            registry.normalize_properties(
                "web.page_viewer",
                {
                    "persist_browser_state": True,
                    "browser_state": {
                        "current_url": "https://example.com",
                        "cookies": ["secret"],
                        "zoom_factor": 9,
                    },
                },
                include_defaults=False,
            ),
            {
                "persist_browser_state": True,
                "browser_state": {
                    "current_url": "https://example.com",
                    "zoom_factor": 3.0,
                },
                "display_mode": "fit_width",
            },
        )
