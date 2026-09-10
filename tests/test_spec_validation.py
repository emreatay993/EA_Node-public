from __future__ import annotations

import unittest
from dataclasses import replace

from ea_node_editor.nodes.node_specs import (
    DynamicPortGroupSpec,
    NodeTypeSpec,
    PortSpec,
    PropertySpec,
)
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.nodes.spec_validation import validate_node_spec
from tests.test_registry_validation import (
    _dynamic_key_factory,
    _dynamic_key_renamer,
    _dynamic_output_ports,
)


class SpecValidationTests(unittest.TestCase):
    def test_dynamic_port_group_declarations_are_validated(self) -> None:
        hidden = PropertySpec(
            "port_ids", "json", ["alpha"], "Port ids", inspector_visible=False
        )
        other_hidden = PropertySpec(
            "other_ids", "json", [], "Other ids", inspector_visible=False
        )
        group = DynamicPortGroupSpec(
            "outputs",
            "port_ids",
            "out",
            _dynamic_output_ports,
            _dynamic_key_factory,
            minimum=1,
        )
        valid_key_rename = replace(
            group,
            rename_mode="key",
            key_renamer=_dynamic_key_renamer,
        )
        valid_spec = NodeTypeSpec(
            "tests.dynamic_key_rename",
            "Dynamic Key Rename",
            ("Tests",),
            "",
            (),
            (hidden,),
            dynamic_port_groups=(valid_key_rename,),
        )
        validate_node_spec(valid_spec, data_types=NodeRegistry().data_types)

        invalid_cases = {
            "group tuple": replace(valid_spec, dynamic_port_groups=[group]),  # type: ignore[arg-type]
            "group type": replace(valid_spec, dynamic_port_groups=(object(),)),  # type: ignore[arg-type]
            "empty group id": replace(group, group_id=""),
            "empty property key": replace(group, property_key=""),
            "unknown property": replace(group, property_key="missing"),
            "visible backing property": group,
            "non-json backing property": group,
            "duplicate group id": (
                group,
                replace(group, property_key="other_ids", direction="in"),
            ),
            "duplicate property key": (
                group,
                replace(group, group_id="inputs", direction="in"),
            ),
            "duplicate direction": (
                group,
                replace(group, group_id="other_outputs", property_key="other_ids"),
            ),
            "negative minimum": replace(group, minimum=-1),
            "maximum below minimum": replace(group, maximum=0),
            "invalid direction": replace(group, direction="neutral"),  # type: ignore[arg-type]
            "invalid rename mode": replace(group, rename_mode="other"),  # type: ignore[arg-type]
            "missing key renamer": replace(group, rename_mode="key"),
            "unexpected key renamer": replace(group, key_renamer=_dynamic_key_renamer),
            "resolver not callable": replace(group, ports_resolver=None),  # type: ignore[arg-type]
            "factory not callable": replace(group, key_factory=None),  # type: ignore[arg-type]
        }
        for name, invalid in invalid_cases.items():
            if name == "group tuple":
                invalid_spec = invalid
            else:
                groups = invalid if isinstance(invalid, tuple) else (invalid,)
                properties = (hidden, other_hidden)
                if name == "visible backing property":
                    properties = (replace(hidden, inspector_visible=True), other_hidden)
                elif name == "non-json backing property":
                    properties = (
                        replace(hidden, type="str", default="alpha"),
                        other_hidden,
                    )
                invalid_spec = replace(
                    valid_spec,
                    type_id=f"tests.dynamic_invalid.{name.replace(' ', '_')}",
                    properties=properties,
                    dynamic_port_groups=groups,
                )
            with self.subTest(name=name), self.assertRaises((TypeError, ValueError)):
                validate_node_spec(invalid_spec, data_types=NodeRegistry().data_types)

    def test_dynamic_port_resolver_failures_are_atomic_validation_errors(self) -> None:
        hidden = PropertySpec(
            "port_ids", "json", ["alpha"], "Port ids", inspector_visible=False
        )
        base_group = DynamicPortGroupSpec(
            "outputs",
            "port_ids",
            "out",
            _dynamic_output_ports,
            _dynamic_key_factory,
            minimum=1,
            maximum=2,
        )
        base_spec = NodeTypeSpec(
            "tests.dynamic_invalid_result",
            "Dynamic Invalid Result",
            ("Tests",),
            "",
            (PortSpec("static", "out", "data", "COREX.DataTypes.Any"),),
            (hidden,),
            dynamic_port_groups=(base_group,),
        )

        def raises(_properties):
            raise RuntimeError("boom")

        invalid_resolvers = {
            "callback": raises,
            "non tuple": lambda _properties: [],
            "non port": lambda _properties: ("alpha",),
            "invalid key": lambda _properties: (
                PortSpec("", "out", "data", "COREX.DataTypes.Any"),
            ),
            "invalid data access": lambda _properties: (
                PortSpec(
                    "alpha",
                    "out",
                    "data",
                    "COREX.DataTypes.Any",
                    data_access="invalid",
                ),  # type: ignore[arg-type]
            ),
            "flow": lambda _properties: (PortSpec("alpha", "out", "flow", "flow"),),
            "wrong direction": lambda _properties: (
                PortSpec(
                    "alpha",
                    "in",
                    "data",
                    "COREX.DataTypes.Any",
                    required=False,
                ),
            ),
            "property default": lambda _properties: (
                PortSpec(
                    "alpha",
                    "out",
                    "data",
                    "COREX.DataTypes.Any",
                    uses_property_default=True,
                ),
            ),
            "static collision": lambda _properties: (
                PortSpec("static", "out", "data", "COREX.DataTypes.Any"),
            ),
            "dynamic collision": lambda _properties: (
                PortSpec("alpha", "out", "data", "COREX.DataTypes.Any"),
                PortSpec("alpha", "out", "data", "COREX.DataTypes.Any"),
            ),
            "below minimum": lambda _properties: (),
            "above maximum": lambda _properties: tuple(
                PortSpec(
                    f"port_{index}",
                    "out",
                    "data",
                    "COREX.DataTypes.Any",
                )
                for index in range(3)
            ),
        }
        for name, resolver in invalid_resolvers.items():
            data_types = NodeRegistry().data_types
            invalid_spec = replace(
                base_spec,
                type_id=f"tests.dynamic_invalid_result.{name.replace(' ', '_')}",
                dynamic_port_groups=(replace(base_group, ports_resolver=resolver),),
            )
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_node_spec(invalid_spec, data_types=data_types)

    def test_validate_node_spec_does_not_mutate_catalog(self) -> None:
        data_types = NodeRegistry().data_types
        before = (data_types.snapshot(), data_types.fingerprint())
        invalid_spec = NodeTypeSpec(
            "tests.validation.pure",
            "Pure Validation",
            ("Tests",),
            "",
            (PortSpec("value", "out", "data", "Packet.Unknown"),),
            (),
        )

        with self.assertRaisesRegex(ValueError, "Packet.Unknown"):
            validate_node_spec(invalid_spec, data_types=data_types)

        self.assertEqual(
            (data_types.snapshot(), data_types.fingerprint()),
            before,
        )
