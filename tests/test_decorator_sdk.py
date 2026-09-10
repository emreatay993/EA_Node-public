from __future__ import annotations

import unittest
from collections.abc import Mapping

from ea_node_editor.runtime_contracts import Interval1D
from ea_node_editor.nodes.category_paths import (
    category_display,
    category_key,
    category_path_matches_prefix,
    normalize_category_path,
)
from ea_node_editor.nodes.decorators import (
    in_port,
    node_type,
    out_port,
    prop_bool,
    prop_enum,
    prop_float,
    prop_int,
    prop_interval_1d,
    prop_json,
    prop_str,
)
from ea_node_editor.nodes.instance_resolution import resolve_instance_ports
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.nodes.node_specs import (
    DynamicPortGroupSpec,
    PortSpec,
    PropertySpec,
    PropertyConditionSpec,
    SettingsGroupItemSpec,
    SettingsGroupSpec,
)


def _decorated_dynamic_ports(properties: Mapping[str, object]) -> tuple[PortSpec, ...]:
    keys = properties.get("output_keys", [])
    if not isinstance(keys, list):
        return ()
    return tuple(PortSpec(str(key), "out", "data", 'COREX.DataTypes.Any') for key in keys)


def _decorated_dynamic_key(properties: Mapping[str, object]) -> str:
    keys = properties.get("output_keys", [])
    return f"output_{len(keys) if isinstance(keys, list) else 0}"


@node_type(
    type_id="tests.decorated",
    display_name="Decorated Node",
    category_path=("Tests",),
    icon="code",
    ports=(
        in_port("input_value", data_type='COREX.DataTypes.Int', required=True),
        out_port("result", data_type='COREX.DataTypes.Int'),
    ),
    properties=(
        prop_int("gain", 2, "Gain"),
        prop_str("name", "demo", "Name"),
        prop_json("payload", {"ok": True}, "Payload"),
    ),
)
class _DecoratedPlugin:
    def execute(self, ctx: ExecutionContext) -> NodeResult:
        value = int(ctx.inputs.get("input_value", 0))
        gain = int(ctx.properties.get("gain", 1))
        return NodeResult(outputs={"result": value * gain})


class DecoratorSdkTests(unittest.TestCase):

    def test_node_type_forwards_dynamic_port_groups_without_constructing_plugin(self) -> None:
        group = DynamicPortGroupSpec(
            group_id="outputs",
            property_key="output_keys",
            direction="out",
            ports_resolver=_decorated_dynamic_ports,
            key_factory=_decorated_dynamic_key,
            minimum=1,
        )
        factory_calls = 0

        @node_type(
            type_id="tests.decorated_dynamic_ports",
            display_name="Decorated Dynamic Ports",
            category_path=("Tests",),
            icon="code",
            ports=(in_port("value", required=False),),
            properties=(
                PropertySpec(
                    "output_keys",
                    "json",
                    ["first"],
                    "Output keys",
                    inspector_visible=False,
                ),
            ),
            dynamic_port_groups=(group,),
        )
        class _DecoratedDynamicPortsPlugin:
            def execute(self, _ctx: ExecutionContext) -> NodeResult:
                return NodeResult()

        def factory() -> _DecoratedDynamicPortsPlugin:
            nonlocal factory_calls
            factory_calls += 1
            return _DecoratedDynamicPortsPlugin()

        registry = NodeRegistry()
        spec = _DecoratedDynamicPortsPlugin.__node_type_spec__
        registry.register_descriptor(spec, factory)

        self.assertEqual(spec.dynamic_port_groups, (group,))
        self.assertEqual(
            [port.key for port in resolve_instance_ports(spec, {"output_keys": ["first", "second"]})],
            ["value", "first", "second"],
        )
        self.assertEqual(DynamicPortGroupSpec.__module__, "ea_node_editor.nodes.node_specs")
        self.assertEqual(factory_calls, 0)

    def test_node_type_forwards_settings_groups(self) -> None:
        options = SettingsGroupSpec(
            group_id="options",
            label="Options",
            items=(SettingsGroupItemSpec(port_key="value"),),
        )

        @node_type(
            type_id="tests.decorated_settings_groups",
            display_name="Decorated Settings Groups",
            category_path=("Tests",),
            icon="code",
            ports=(in_port("value", required=False),),
            properties=(),
            settings_groups=(options,),
        )
        class _DecoratedSettingsGroupsPlugin:
            def execute(self, _ctx: ExecutionContext) -> NodeResult:
                return NodeResult()

        registry = NodeRegistry()
        registry.register(lambda: _DecoratedSettingsGroupsPlugin())

        self.assertEqual(registry.get_spec("tests.decorated_settings_groups").settings_groups, (options,))

    def test_node_type_forwards_internal_solution_reuse_scope(self) -> None:
        @node_type(
            type_id="tests.decorated_solution_scope",
            display_name="Decorated Solution Scope",
            category_path=("Tests",),
            icon="code",
            ports=(),
            properties=(),
            solution_reuse_scope="session",
        )
        class _DecoratedSolutionScopePlugin:
            def execute(self, _ctx: ExecutionContext) -> NodeResult:
                return NodeResult()

        self.assertEqual(
            _DecoratedSolutionScopePlugin.__node_type_spec__.solution_reuse_scope,
            "session",
        )

    def test_nested_category_sdk_decorator_accepts_single_level_path(self) -> None:
        registry = NodeRegistry()

        @node_type(
            type_id="tests.decorated_single_category_path",
            display_name="Decorated Single Category Path",
            category_path=("  Tests  ",),
            icon="code",
            ports=(),
            properties=(),
        )
        class _DecoratedSingleCategoryPathPlugin:
            def execute(self, _ctx: ExecutionContext) -> NodeResult:
                return NodeResult()

        registry.register(lambda: _DecoratedSingleCategoryPathPlugin())
        spec = registry.get_spec("tests.decorated_single_category_path")

        self.assertEqual(spec.category_path, ("Tests",))
        self.assertEqual(spec.category, "Tests")

    def test_nested_category_sdk_helpers_normalize_display_key_and_prefix_match(self) -> None:
        path = (" Parent ", "Child", "Leaf ")

        self.assertEqual(normalize_category_path(path), ("Parent", "Child", "Leaf"))
        self.assertEqual(category_display(path), "Parent > Child > Leaf")
        self.assertEqual(category_key(path), category_key(("Parent", "Child", "Leaf")))
        self.assertNotEqual(category_key(path), category_display(path))
        self.assertTrue(category_path_matches_prefix(path, ("Parent", "Child")))
        self.assertFalse(category_path_matches_prefix(path, ("Parent", "Other")))

    def test_port_helpers_preserve_direction_and_connection_flags(self) -> None:
        inbound = in_port("incoming", kind="flow", data_type="flow", allow_multiple_connections=True)
        outbound = out_port(
            "outgoing",
            data_access="tree",
            exposed=False,
        )
        union_input = in_port(
            "union",
            data_type="COREX.DataTypes.String",
            accepted_data_types=("COREX.DataTypes.Int",),
            required=False,
        )

        self.assertEqual(inbound.direction, "in")
        self.assertEqual(inbound.kind, "flow")
        self.assertEqual(inbound.data_type, "flow")
        self.assertTrue(inbound.allow_multiple_connections)

        self.assertEqual(outbound.direction, "out")
        self.assertEqual(outbound.kind, "data")
        self.assertEqual(
            outbound.data_type,
            "COREX.DataTypes.Any",
        )
        self.assertEqual(outbound.data_access, "tree")
        self.assertFalse(outbound.exposed)
        self.assertEqual(
            union_input.accepted_data_types,
            ("COREX.DataTypes.Int",),
        )

    def test_property_helpers_build_expected_specs(self) -> None:
        enabled = prop_bool("enabled", True, "Enabled", inspector_editor="toggle")
        threshold = prop_float("threshold", 1.5, "Threshold")
        mode = prop_enum(
            "mode",
            "fast",
            "Mode",
            values=("fast", "safe"),
            inline_editor="enum",
            inspector_editor="enum",
            searchable=True,
        )
        condition = PropertyConditionSpec("mode", ("safe",))
        sectors = prop_int("sectors", 2, "Sectors", enabled_when=condition)
        interval = prop_interval_1d(
            "result_bound",
            Interval1D(10.0, 0.0),
            "Result bound",
            minimum=0.0,
            maximum=100.0,
            step=0.001,
            direction="decreasing",
            enabled_when=condition,
        )

        self.assertEqual(enabled.type, "bool")
        self.assertTrue(enabled.default)
        self.assertEqual(enabled.inspector_editor, "toggle")

        self.assertEqual(threshold.type, "float")
        self.assertAlmostEqual(float(threshold.default), 1.5, places=3)

        self.assertEqual(mode.type, "enum")
        self.assertEqual(mode.default, "fast")
        self.assertEqual(mode.enum_values, ("fast", "safe"))
        self.assertTrue(mode.searchable)

        self.assertEqual(sectors.enabled_when, condition)
        self.assertEqual(interval.type, "interval_1d")
        self.assertEqual(interval.default, Interval1D(10.0, 0.0))
        self.assertEqual(interval.inline_editor, "interval_slider")
        self.assertEqual(interval.interval_direction, "decreasing")
        self.assertEqual(interval.enabled_when, condition)

    def test_decorator_builds_valid_spec_and_executes(self) -> None:
        registry = NodeRegistry()
        registry.register(_DecoratedPlugin)
        spec = registry.get_spec("tests.decorated")

        self.assertEqual(spec.display_name, "Decorated Node")
        self.assertEqual(spec.ports[0].key, "input_value")
        self.assertTrue(spec.ports[0].required)
        self.assertEqual(spec.properties[0].key, "gain")

        plugin = registry.create("tests.decorated")
        result = plugin.execute(
            ExecutionContext(
                run_id="run",
                node_id="node",
                workspace_id="ws",
                inputs={"input_value": 4},
                properties={"gain": 3},
                emit_log=lambda _level, _message: None,
            )
        )
        self.assertEqual(result.outputs["result"], 12)

    def test_decorator_defaults_are_registry_normalized(self) -> None:
        registry = NodeRegistry()
        registry.register(_DecoratedPlugin)

        defaults = registry.default_properties("tests.decorated")

        self.assertEqual(defaults["gain"], 2)
        self.assertEqual(defaults["name"], "demo")
        self.assertEqual(defaults["payload"], {"ok": True})


if __name__ == "__main__":
    unittest.main()
