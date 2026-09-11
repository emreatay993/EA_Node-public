# Purpose: Verify registry validation, graph mutation, normalization, compatibility, and metadata contracts.
# Map: subsystems/nodes_registry_builtins.md
# Tests: this file
# Landmarks: _factory; RegistryValidationTests; test_settings_group_contract_and_registry_validation; test_default_registry_has_canonical_type_inventory_and_declared_special_cases

from __future__ import annotations

import unittest
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from ea_node_editor.runtime_contracts import (
    DOUBLE_DATA_TYPE_ID,
    GRAPH_DATA_TYPE_ID,
    INTEGER_DATA_TYPE_ID,
    INTERVAL_1D_GRAPH_DATA_TYPE_ID,
    STRING_DATA_TYPE_ID,
    DataConversionSpec,
    DataTypeFamilySpec,
    DataTypeSpec,
    DataTree,
    Interval1D,
    TypedInlineValue,
    serialize_runtime_value,
)
import ea_node_editor.graph.invariant_kernel as invariant_kernel
from ea_node_editor.graph.invariant_kernel import (
    GraphInvariantKernel,
    RegistryValidationPassMemo,
)
from ea_node_editor.graph.subnode_contract import (
    SUBNODE_INPUT_TYPE_ID,
    SUBNODE_OUTPUT_TYPE_ID,
    SUBNODE_PIN_ACCEPTED_DATA_TYPES_PROPERTY,
    SUBNODE_PIN_PORT_KEY,
    SUBNODE_TYPE_ID,
    default_subnode_pin_label,
    resolve_subnode_pin_definition,
)
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.workspace_state import WorkspaceData, WorkspaceSnapshot
from ea_node_editor.graph.records import EdgeInstance, NodeInstance
from ea_node_editor.graph.fragment_payloads import build_graph_fragment_payload
from ea_node_editor.graph.registry_normalization import normalize_project_for_registry
from ea_node_editor.graph.transform_fragment_ops import (
    build_subtree_fragment_payload_data,
    encode_fragment_external_parent_id,
    insert_graph_fragment,
)
from ea_node_editor.graph.transform_grouping_ops import (
    group_selection_into_subnode,
    ungroup_subnode,
)
from ea_node_editor.addons.tabular_data.input_node import (
    TABULAR_DATA_INPUT_NODE_TYPE_ID,
)
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.solution_provenance import SolutionProvenanceInputSpec
from ea_node_editor.nodes.builtins.icon_catalog import builtin_node_type
from ea_node_editor.nodes.builtins.integrations_ssh_sftp import (
    SSH_SFTP_HOST_DATA_TYPE_ID,
    SSH_SFTP_SECRET_DATA_TYPE_ID,
)
from ea_node_editor.nodes.builtins.plot import PLOT_NODE_DESCRIPTORS, PLOT_NODE_TYPE_IDS
from ea_node_editor.nodes.builtins.fem_contracts import LOAD_STEP_DATA_TYPE_ID
from ea_node_editor.nodes.builtins.web_viewer import WEB_PAGE_VIEWER_TYPE_ID
import ea_node_editor.nodes.node_specs as node_specs
import ea_node_editor.nodes.plugin_contracts as plugin_contracts
from ea_node_editor.nodes.decorators import (
    in_port,
    node_type,
    prop_enum,
    prop_int,
    prop_interval_1d,
)
from ea_node_editor.nodes.function_plugin import (
    INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    PythonFunctionRef,
)
from ea_node_editor.nodes.readiness import (
    evaluate_node_readiness,
    readiness_value_is_present,
)
from ea_node_editor.nodes.instance_resolution import resolve_instance_ports
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.nodes.execution_context import NodeResult
from ea_node_editor.nodes.node_specs import (
    DynamicPortGroupSpec,
    NodeRenderQualitySpec,
    NodeTypeSpec,
    PortSpec,
    PropertySpec,
    PropertyConditionSpec,
    ReadinessRequirementSpec,
    SettingsGroupItemSpec,
    SettingsGroupSpec,
)
from ea_node_editor.nodes.plugin_contracts import PluginDescriptor, PluginProvenance


class _Plugin:
    def __init__(self, spec: NodeTypeSpec) -> None:
        self._spec = spec

    def spec(self) -> NodeTypeSpec:
        return self._spec

    def execute(self, _ctx) -> NodeResult:  # noqa: ANN001
        return NodeResult()


def _factory(spec: NodeTypeSpec):
    return lambda: _Plugin(spec)


def _dynamic_output_ports(properties: Mapping[str, object]) -> tuple[PortSpec, ...]:
    keys = properties.get("port_ids", [])
    if not isinstance(keys, list):
        return ()
    limit = properties.get("port_limit", len(keys))
    if isinstance(limit, int) and not isinstance(limit, bool):
        keys = keys[:limit]
    return tuple(
        PortSpec(str(key), "out", "data", "COREX.DataTypes.Any")
        for key in keys
    )


def _dynamic_input_ports(properties: Mapping[str, object]) -> tuple[PortSpec, ...]:
    keys = properties.get("input_ids", [])
    if not isinstance(keys, list):
        return ()
    return tuple(
        PortSpec(
            str(key),
            "in",
            "data",
            "COREX.DataTypes.Any",
            required=False,
        )
        for key in keys
    )


def _dynamic_key_factory(properties: Mapping[str, object]) -> str:
    keys = properties.get("port_ids", [])
    return f"port_{len(keys) if isinstance(keys, list) else 0}"


def _dynamic_key_renamer(
    _properties: Mapping[str, object],
    _port_key: str,
    value: str,
) -> str:
    return value.strip()


class RegistryValidationTests(unittest.TestCase):
    def test_readiness_evaluator_covers_required_grouped_conditional_and_property_defaults(
        self,
    ) -> None:
        spec = NodeTypeSpec(
            type_id="tests.readiness",
            display_name="Readiness",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec(
                    "mandatory",
                    "in",
                    "data",
                    "COREX.DataTypes.String",
                    label="Mandatory Input",
                    required=True,
                ),
                PortSpec(
                    "configured",
                    "in",
                    "data",
                    "COREX.DataTypes.String",
                    label="Configured Input",
                    required=True,
                    uses_property_default=True,
                ),
                PortSpec(
                    "left",
                    "in",
                    "data",
                    "COREX.DataTypes.String",
                    label="Left",
                    required=False,
                ),
                PortSpec(
                    "right",
                    "in",
                    "data",
                    "COREX.DataTypes.String",
                    label="Right",
                    required=False,
                ),
                PortSpec(
                    "trigger",
                    "in",
                    "data",
                    "COREX.DataTypes.Bool",
                    label="Trigger",
                    required=False,
                ),
            ),
            properties=(
                PropertySpec("configured", "str", "preset", "Configured Input"),
                PropertySpec("zero", "int", 0, "Zero"),
                PropertySpec("disabled", "bool", False, "Disabled"),
                PropertySpec("mode", "enum", "off", "Mode", enum_values=("off", "on")),
                PropertySpec("gate", "str", "", "Gate"),
                PropertySpec("detail", "str", "", "Detail"),
                PropertySpec("secret", "str", "", "Secret"),
            ),
            readiness_requirements=(
                ReadinessRequirementSpec(any_of_ports=("left", "right")),
                ReadinessRequirementSpec(any_of_properties=("zero",)),
                ReadinessRequirementSpec(any_of_properties=("disabled",)),
                ReadinessRequirementSpec(
                    any_of_properties=("detail",),
                    when_properties=(
                        PropertyConditionSpec("mode", ("on",)),
                        PropertyConditionSpec("gate"),
                    ),
                ),
                ReadinessRequirementSpec(
                    any_of_properties=("secret",),
                    when_ports_present=("trigger",),
                ),
            ),
        )
        properties = {
            "configured": "preset",
            "zero": 0,
            "disabled": False,
            "mode": "off",
            "gate": "",
            "detail": "",
            "secret": "",
        }

        issues = evaluate_node_readiness(
            spec,
            port_has_value={},
            overridden_port_keys=(),
            properties=properties,
        )

        self.assertEqual(
            [issue.code for issue in issues], ["required_input_waiting"] * 2
        )
        self.assertEqual(
            [issue.target_keys for issue in issues], [("mandatory",), ("left", "right")]
        )
        self.assertEqual(issues[0].target_labels, ("Mandatory Input",))
        self.assertIn("did not receive any data yet", issues[0].message)
        self.assertIn("provide at least one of: Left, Right", issues[1].message)
        self.assertTrue(readiness_value_is_present(False))
        self.assertTrue(readiness_value_is_present(0))
        self.assertFalse(readiness_value_is_present("  "))
        self.assertFalse(readiness_value_is_present([]))

        changed = evaluate_node_readiness(
            spec,
            port_has_value={"right": True, "trigger": True},
            overridden_port_keys=("configured",),
            properties={**properties, "mode": "on", "gate": "ready"},
        )
        self.assertEqual(
            [issue.target_keys for issue in changed],
            [("mandatory",), ("configured",), ("detail",), ("secret",)],
        )
        self.assertIn("Detail setting is empty", changed[2].message)

    def test_registry_validates_declarative_readiness_without_constructing_plugins(
        self,
    ) -> None:
        requirement = ReadinessRequirementSpec(
            any_of_ports=("left", "right"),
            when_properties=(PropertyConditionSpec("mode", ("on",)),),
        )
        valid_spec = NodeTypeSpec(
            type_id="tests.readiness_validation",
            display_name="Readiness Validation",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec(
                    "left",
                    "in",
                    "data",
                    "COREX.DataTypes.String",
                    required=False,
                ),
                PortSpec(
                    "right",
                    "in",
                    "data",
                    "COREX.DataTypes.String",
                    required=False,
                ),
                PortSpec("result", "out", "data", "COREX.DataTypes.String"),
            ),
            properties=(
                PropertySpec("mode", "enum", "off", "Mode", enum_values=("off", "on")),
                PropertySpec("setting", "str", "", "Setting"),
            ),
            readiness_requirements=(requirement,),
        )
        factory_calls = 0

        def factory() -> _Plugin:
            nonlocal factory_calls
            factory_calls += 1
            return _Plugin(valid_spec)

        registry = NodeRegistry()
        registry.register_descriptor(valid_spec, factory)
        self.assertEqual(factory_calls, 0)
        self.assertIsNone(in_port("undeclared").required)
        self.assertEqual(
            registry.get_spec(valid_spec.type_id).readiness_requirements, (requirement,)
        )

        invalid_specs = {
            "undeclared active input": replace(
                valid_spec,
                ports=(
                    PortSpec("left", "in", "data", "COREX.DataTypes.String"),
                ),
                readiness_requirements=(),
            ),
            "required output": replace(
                valid_spec,
                ports=(
                    PortSpec(
                        "result",
                        "out",
                        "data",
                        "COREX.DataTypes.String",
                        required=True,
                    ),
                ),
                readiness_requirements=(),
            ),
            "empty rule": replace(
                valid_spec,
                readiness_requirements=(ReadinessRequirementSpec(),),
            ),
            "unknown target": replace(
                valid_spec,
                readiness_requirements=(
                    ReadinessRequirementSpec(any_of_ports=("missing",)),
                ),
            ),
            "duplicate rule": replace(
                valid_spec,
                readiness_requirements=(requirement, requirement),
            ),
            "invalid enum condition": replace(
                valid_spec,
                readiness_requirements=(
                    replace(
                        requirement,
                        when_properties=(PropertyConditionSpec("mode", ("missing",)),),
                    ),
                ),
            ),
            "contradictory property": replace(
                valid_spec,
                readiness_requirements=(
                    ReadinessRequirementSpec(
                        any_of_properties=("setting",),
                        when_properties=(PropertyConditionSpec("setting"),),
                    ),
                ),
            ),
            "malformed requirement collection": replace(
                valid_spec,
                readiness_requirements=[requirement],  # type: ignore[arg-type]
            ),
        }
        for case, invalid_spec in invalid_specs.items():
            with self.subTest(case=case), self.assertRaises((TypeError, ValueError)):
                NodeRegistry().register_descriptor(invalid_spec, factory)
            self.assertEqual(factory_calls, 0)

    def test_builtin_node_type_decorator_forwards_readiness_requirements(self) -> None:
        requirement = ReadinessRequirementSpec(any_of_ports=("value",))

        @builtin_node_type(
            type_id="core.logger",
            display_name="Decorated Readiness",
            category_path=("Tests",),
            ports=(in_port("value", required=False),),
            properties=(),
            readiness_requirements=(requirement,),
        )
        class _DecoratedReadinessNode:
            def execute(self, _ctx) -> NodeResult:  # noqa: ANN001
                return NodeResult()

        registry = NodeRegistry()
        registry.register(lambda: _DecoratedReadinessNode())

        self.assertEqual(
            registry.get_spec("core.logger").readiness_requirements,
            (requirement,),
        )

    def test_property_default_ports_require_compatible_same_key_properties(
        self,
    ) -> None:
        value_port = PortSpec(
            "value",
            "in",
            "data",
            "COREX.DataTypes.String",
            required=False,
            uses_property_default=True,
        )
        value_property = PropertySpec("value", "str", "fallback", "Value")
        valid_spec = NodeTypeSpec(
            type_id="tests.property_default",
            display_name="Property Default",
            category_path=("Tests",),
            icon="",
            ports=(value_port,),
            properties=(value_property,),
        )

        registry = NodeRegistry()
        registry.register_descriptor(valid_spec, _factory(valid_spec))
        self.assertTrue(
            registry.get_spec(valid_spec.type_id).ports[0].uses_property_default
        )
        self.assertTrue(
            in_port("value", uses_property_default=True).uses_property_default
        )
        self.assertFalse(
            PortSpec(
                "plain", "in", "data", "COREX.DataTypes.String"
            ).uses_property_default
        )

        tree_default = serialize_runtime_value(DataTree.from_item("fallback"))
        tree_spec = replace(
            valid_spec,
            type_id="tests.property_default_tree",
            ports=(replace(value_port, data_access="tree"),),
            properties=(PropertySpec("value", "json", tree_default, "Value"),),
        )
        NodeRegistry().register_descriptor(tree_spec, _factory(tree_spec))

        coercible_spec = replace(
            valid_spec,
            type_id="tests.property_default_coercible",
            ports=(replace(value_port, data_type="COREX.DataTypes.Int"),),
            properties=(PropertySpec("value", "str", "42", "Value"),),
        )
        coercible_registry = NodeRegistry()
        coercible_registry.register_descriptor(
            coercible_spec,
            _factory(coercible_spec),
        )
        self.assertEqual(
            coercible_registry.get_spec(coercible_spec.type_id).type_id,
            coercible_spec.type_id,
        )

        invalid_specs = {
            "same-key property": replace(valid_spec, properties=()),
            "list sequence": replace(
                valid_spec,
                ports=(replace(value_port, data_access="list"),),
            ),
            "tree marker access": replace(
                valid_spec,
                properties=(PropertySpec("value", "json", tree_default, "Value"),),
            ),
            "active data input": replace(
                valid_spec,
                ports=(replace(value_port, direction="out"),),
            ),
        }
        for case, invalid_spec in invalid_specs.items():
            with self.subTest(case=case), self.assertRaises(ValueError):
                NodeRegistry().register_descriptor(invalid_spec, _factory(invalid_spec))

    def test_settings_group_contract_and_registry_validation(self) -> None:
        width_port = PortSpec(
            "width", "in", "data", "COREX.DataTypes.Int", required=False
        )
        title_port = PortSpec(
            "title", "in", "data", "COREX.DataTypes.String", required=False
        )
        image_port = PortSpec(
            "image",
            "out",
            "data",
            "COREX.DataTypes.Any",
        )
        width_property = PropertySpec(
            key="width",
            type="int",
            default=600,
            label="Width",
            minimum=2,
            maximum=3840,
            inline_editor="slider",
        )
        title_property = PropertySpec(
            key="title",
            type="str",
            default="",
            label="Title",
            inline_editor="text",
        )
        general_group = SettingsGroupSpec(
            group_id="general",
            label="General Options",
            items=(
                SettingsGroupItemSpec(port_key="width", property_key="width"),
                SettingsGroupItemSpec(property_key="title"),
            ),
        )
        plot_group = SettingsGroupSpec(
            group_id="plot.options",
            label="Plot Options",
            items=(SettingsGroupItemSpec(port_key="title"),),
        )
        valid_spec = NodeTypeSpec(
            type_id="tests.settings_groups",
            display_name="Settings Groups",
            category_path=("Tests",),
            icon="",
            ports=(width_port, title_port, image_port),
            properties=(width_property, title_property),
            settings_groups=(general_group, plot_group),
            default_expanded_settings_group_ids=("general",),
        )

        registry = NodeRegistry()
        registry.register_descriptor(valid_spec, _factory(valid_spec))
        self.assertEqual(
            registry.get_spec(valid_spec.type_id).settings_groups,
            (general_group, plot_group),
        )
        self.assertEqual(
            registry.get_spec(valid_spec.type_id).default_expanded_settings_group_ids,
            ("general",),
        )

        invalid_specs = {
            "active nodes only": replace(valid_spec, runtime_behavior="passive"),
            "stable id": replace(
                valid_spec,
                settings_groups=(replace(general_group, group_id="Bad ID"),),
            ),
            "unique ids": replace(
                valid_spec, settings_groups=(general_group, general_group)
            ),
            "nonempty label": replace(
                valid_spec,
                settings_groups=(replace(general_group, label=""),),
            ),
            "nonempty items": replace(
                valid_spec,
                settings_groups=(replace(general_group, items=()),),
            ),
            "item identifies content": replace(
                valid_spec,
                settings_groups=(
                    replace(general_group, items=(SettingsGroupItemSpec(),)),
                ),
            ),
            "item keys are strings": replace(
                valid_spec,
                settings_groups=(
                    replace(general_group, items=(SettingsGroupItemSpec(port_key=42),)),  # type: ignore[arg-type]
                ),
            ),
            "unique port membership": replace(
                valid_spec,
                settings_groups=(
                    general_group,
                    replace(
                        plot_group, items=(SettingsGroupItemSpec(port_key="width"),)
                    ),
                ),
            ),
            "unique property membership": replace(
                valid_spec,
                settings_groups=(
                    general_group,
                    replace(
                        plot_group, items=(SettingsGroupItemSpec(property_key="title"),)
                    ),
                ),
            ),
            "input ports only": replace(
                valid_spec,
                settings_groups=(
                    replace(
                        general_group, items=(SettingsGroupItemSpec(port_key="image"),)
                    ),
                ),
            ),
            "known ports": replace(
                valid_spec,
                settings_groups=(
                    replace(
                        general_group,
                        items=(SettingsGroupItemSpec(port_key="missing"),),
                    ),
                ),
            ),
            "known properties": replace(
                valid_spec,
                settings_groups=(
                    replace(
                        general_group,
                        items=(SettingsGroupItemSpec(property_key="missing"),),
                    ),
                ),
            ),
            "inline editor required": replace(
                valid_spec,
                properties=(
                    *valid_spec.properties,
                    PropertySpec("plain", "str", "", "Plain"),
                ),
                settings_groups=(
                    replace(
                        general_group,
                        items=(SettingsGroupItemSpec(property_key="plain"),),
                    ),
                ),
            ),
            "paired override relationship": replace(
                valid_spec,
                settings_groups=(
                    replace(
                        general_group,
                        items=(
                            SettingsGroupItemSpec(
                                port_key="width", property_key="title"
                            ),
                        ),
                    ),
                ),
            ),
            "known default expanded ids": replace(
                valid_spec,
                default_expanded_settings_group_ids=("missing",),
            ),
            "default expanded declaration order": replace(
                valid_spec,
                default_expanded_settings_group_ids=("plot.options", "general"),
            ),
            "default expanded requires groups": replace(
                valid_spec,
                settings_groups=(),
                default_expanded_settings_group_ids=("general",),
            ),
        }
        for case, invalid_spec in invalid_specs.items():
            with self.subTest(case=case), self.assertRaises((TypeError, ValueError)):
                NodeRegistry().register_descriptor(invalid_spec, _factory(invalid_spec))

    def test_node_documentation_metadata_defaults_and_normalization(self) -> None:
        plain_port = PortSpec(
            "value", "out", "data", "COREX.DataTypes.Any"
        )
        plain_spec = NodeTypeSpec(
            type_id="tests.documentation_defaults",
            display_name="Documentation Defaults",
            category_path=("Tests",),
            icon="",
            ports=(plain_port,),
            properties=(),
        )
        self.assertEqual(plain_port.description, "")
        self.assertEqual(plain_spec.keywords, ())
        self.assertEqual(plain_spec.settings_groups, ())
        self.assertEqual(plain_spec.default_expanded_settings_group_ids, ())

        documented_port = PortSpec(
            "value",
            "out",
            "data",
            "COREX.DataTypes.Any",
            description="The value produced by the node.",
        )
        documented_spec = NodeTypeSpec(
            type_id="tests.documentation",
            display_name="Documentation",
            category_path=("Tests",),
            icon="",
            ports=(documented_port,),
            properties=(),
            keywords=("docs", "metadata"),
        )
        self.assertEqual(documented_port.description, "The value produced by the node.")
        self.assertEqual(documented_spec.keywords, ("docs", "metadata"))

        with self.assertRaises(ValueError):
            PortSpec(
                "value",
                "out",
                "data",
                "COREX.DataTypes.Any",
                description=" padded ",
            )
        for invalid_keywords in ((" padded",), ("",), ("same", "same"), (42,)):
            with (
                self.subTest(invalid_keywords=invalid_keywords),
                self.assertRaises((TypeError, ValueError)),
            ):
                NodeTypeSpec(
                    type_id="tests.bad_keywords",
                    display_name="Bad Keywords",
                    category_path=("Tests",),
                    icon="",
                    ports=(),
                    properties=(),
                    keywords=invalid_keywords,  # type: ignore[arg-type]
                )

        @node_type(
            type_id="tests.decorated_docs",
            display_name="Decorated Docs",
            category_path=("Tests",),
            icon="",
            ports=(documented_port,),
            properties=(),
            keywords=("decorator",),
        )
        class _DecoratedDocsPlugin(_Plugin):
            pass

        @builtin_node_type(
            type_id="core.constant",
            display_name="Built-in Decorated Docs",
            category_path=("Tests",),
            ports=(documented_port,),
            properties=(),
            keywords=("built-in",),
        )
        class _BuiltInDecoratedDocsPlugin(_Plugin):
            pass

        self.assertEqual(_DecoratedDocsPlugin.spec(None).keywords, ("decorator",))
        self.assertEqual(_BuiltInDecoratedDocsPlugin.spec(None).keywords, ("built-in",))

    def test_workspace_snapshot_excludes_mutation_revision(self) -> None:
        self.assertIn("mutation_revision", WorkspaceData.__dataclass_fields__)
        self.assertNotIn("mutation_revision", WorkspaceSnapshot.__dataclass_fields__)

        workspace = WorkspaceData(workspace_id="ws_test", name="Workspace")
        snapshot = workspace.capture_snapshot()

        self.assertFalse(hasattr(snapshot, "mutation_revision"))

        same_workspace = WorkspaceData(workspace_id="ws_test", name="Workspace")
        same_workspace.bump_mutation_revision()
        self.assertEqual(workspace, same_workspace)

        before_revision_only = workspace.capture_snapshot()
        workspace.bump_mutation_revision()
        after_revision_only = workspace.capture_snapshot()
        self.assertEqual(before_revision_only, after_revision_only)

    def test_duplicate_workspace_receives_independent_live_graph_copy(self) -> None:
        model = GraphModel()
        source = model.active_workspace
        node = model.add_node(
            source.workspace_id,
            "core.logger",
            "Logger",
            10.0,
            20.0,
            properties={"message": "source"},
        )

        duplicate = model.duplicate_workspace(source.workspace_id)
        duplicate_node = duplicate.nodes[node.node_id]

        self.assertEqual(duplicate_node.properties, {"message": "source"})
        duplicate_node.properties["message"] = "duplicate"
        self.assertEqual(source.nodes[node.node_id].properties, {"message": "source"})

    def test_workspace_snapshot_restores_live_graph_state_only(self) -> None:
        workspace = WorkspaceData(workspace_id="ws_test", name="Workspace")
        node = NodeInstance(
            node_id="node_logger",
            type_id="core.logger",
            title="Logger",
            x=10.0,
            y=20.0,
        )
        workspace.nodes[node.node_id] = node

        snapshot = workspace.capture_snapshot()

        workspace.nodes[node.node_id].title = "Changed"

        workspace.restore_snapshot(snapshot)

        self.assertEqual(workspace.nodes[node.node_id].title, "Logger")

    def test_workspace_snapshot_equality_tracks_live_graph_state(self) -> None:
        workspace = WorkspaceData(workspace_id="ws_test", name="Workspace")
        before = workspace.capture_snapshot()

        workspace.nodes["node_logger"] = NodeInstance(
            node_id="node_logger",
            type_id="core.logger",
            title="Logger",
            x=10.0,
            y=20.0,
        )
        after = workspace.capture_snapshot()

        self.assertNotEqual(before, after)

    def test_graph_invariant_kernel_validation_pass_memo_reuses_node_view_ports_and_edge_tuple(
        self,
    ) -> None:
        class _CountingEdgeValues:
            def __init__(self, edges) -> None:  # noqa: ANN001
                self._edges = tuple(edges)
                self.iterations = 0

            def __iter__(self):  # noqa: ANN204
                self.iterations += 1
                return iter(self._edges)

        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        source = model.add_node(
            workspace.workspace_id, "io.path_pointer", "Path", 0.0, 0.0
        )
        target = model.add_node(
            workspace.workspace_id, "io.file_read", "Read File", 240.0, 0.0
        )
        edge_values = _CountingEdgeValues(workspace.edges.values())
        kernel = GraphInvariantKernel(
            registry=registry,
            workspace_nodes=workspace.nodes,
            workspace_edges=edge_values,
        )
        memo = RegistryValidationPassMemo()

        with patch.object(
            invariant_kernel, "effective_ports", wraps=invariant_kernel.effective_ports
        ) as spy:
            resolved_nodes = kernel.resolve_registry_nodes(memo=memo)
            first = kernel.validate_registry_edge(
                source_node_id=source.node_id,
                source_port_key="path",
                target_node_id=target.node_id,
                target_port_key="path",
                resolved_nodes=resolved_nodes,
                memo=memo,
                require_source_output=True,
                require_target_input=True,
                require_exposed_ports=True,
                require_compatible_ports=True,
            )
            second = kernel.validate_registry_edge(
                source_node_id=source.node_id,
                source_port_key="path",
                target_node_id=target.node_id,
                target_port_key="path",
                resolved_nodes=resolved_nodes,
                memo=memo,
                require_source_output=True,
                require_target_input=True,
                require_exposed_ports=True,
                require_compatible_ports=True,
            )

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(edge_values.iterations, 1)
        self.assertEqual(spy.call_count, 2)
        self.assertEqual(
            set(memo.effective_ports_by_node_id), {source.node_id, target.node_id}
        )
        self.assertIn((source.node_id, "path"), memo.port_by_node_and_key)
        self.assertIn((target.node_id, "path"), memo.port_by_node_and_key)

    def test_validated_mutation_prune_edges_keeps_data_fan_in_and_removes_exact_duplicates(
        self,
    ) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        first_source = model.add_node(
            workspace.workspace_id, "core.constant", "Source 1", 0.0, 0.0
        )
        second_source = model.add_node(
            workspace.workspace_id, "core.constant", "Source 2", 0.0, 120.0
        )
        target = model.add_node(
            workspace.workspace_id, "core.logger", "Logger", 260.0, 40.0
        )
        kept_edge = model.add_edge(
            workspace.workspace_id,
            first_source.node_id,
            "as_text",
            target.node_id,
            "message",
        )
        second_edge = model.add_edge(
            workspace.workspace_id,
            second_source.node_id,
            "as_text",
            target.node_id,
            "message",
        )
        duplicate_edge = EdgeInstance(
            edge_id="edge_duplicate_data",
            source_node_id=first_source.node_id,
            source_port_key="as_text",
            target_node_id=target.node_id,
            target_port_key="message",
        )
        workspace.edges[duplicate_edge.edge_id] = duplicate_edge
        mutations = model.validated_mutations(workspace.workspace_id, registry)

        removed_edge_ids = mutations._prune_edges_for_nodes({target.node_id})

        self.assertIn(kept_edge.edge_id, workspace.edges)
        self.assertIn(second_edge.edge_id, workspace.edges)
        self.assertNotIn(duplicate_edge.edge_id, workspace.edges)
        self.assertEqual(removed_edge_ids, [duplicate_edge.edge_id])

    def test_register_rejects_duplicate_port_keys(self) -> None:
        registry = NodeRegistry()
        spec = NodeTypeSpec(
            type_id="tests.dup_ports",
            display_name="Dup Ports",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec(
                    "value", "out", "data", "COREX.DataTypes.Any"
                ),
                PortSpec(
                    "value",
                    "in",
                    "data",
                    "COREX.DataTypes.Any",
                    required=False,
                ),
            ),
            properties=(),
        )
        with self.assertRaises(ValueError):
            registry.register(_factory(spec))

    def test_register_descriptor_stores_spec_without_instantiating_factory(
        self,
    ) -> None:
        registry = NodeRegistry()
        spec = NodeTypeSpec(
            type_id="tests.descriptor",
            display_name="Descriptor",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec(
                    "value", "out", "data", "COREX.DataTypes.Any"
                ),
            ),
            properties=(),
        )
        factory_calls = 0

        def _descriptor_factory() -> _Plugin:
            nonlocal factory_calls
            factory_calls += 1
            return _Plugin(spec)

        provenance = PluginProvenance(
            kind="file",
            source_path=Path("C:/packet/tests/descriptor.py"),
        )
        registry.register_descriptor(
            PluginDescriptor(
                spec=spec,
                factory=_descriptor_factory,
                provenance=provenance,
            )
        )

        self.assertEqual(factory_calls, 0)
        self.assertEqual(
            registry.get_spec("tests.descriptor").display_name, "Descriptor"
        )
        self.assertEqual(
            registry.get_descriptor("tests.descriptor").provenance, provenance
        )
        self.assertEqual(registry.all_descriptors()[0].provenance, provenance)
        self.assertEqual(
            registry.create("tests.descriptor").spec().type_id, "tests.descriptor"
        )
        self.assertEqual(factory_calls, 1)

    def test_persistent_typed_properties_copy_without_static_port_catalog_resolution(
        self,
    ) -> None:
        inline_type_id = "tests.registry.InlinePayload"
        registry = NodeRegistry()
        registry.data_types.register_many(
            types=(
                DataTypeSpec(
                    inline_type_id,
                    "Inline Payload",
                    "graph",
                    lambda value: (
                        type(value) is dict
                        and set(value) == {"nested"}
                        and type(value["nested"]) is list
                    ),
                    parents=(GRAPH_DATA_TYPE_ID,),
                    carriers=frozenset({"inline"}),
                    persistence="inline",
                ),
            ),
            owner_id="tests.registry_typed_properties",
        )
        declared_default = TypedInlineValue(
            inline_type_id,
            1,
            {"nested": [1, 2]},
        )
        typed_property = PropertySpec(
            "value",
            "json",
            declared_default,
            "Value",
            persistence_data_type_id=inline_type_id,
        )
        static_spec = NodeTypeSpec(
            "tests.registry.typed_static",
            "Typed Static",
            ("Tests",),
            "",
            (PortSpec("result", "out", "data", GRAPH_DATA_TYPE_ID),),
            (typed_property,),
        )
        registry.register_descriptor(static_spec, _factory(static_spec))

        self.assertEqual(
            resolve_instance_ports(static_spec, {"value": declared_default}),
            static_spec.ports,
        )
        first = registry.default_properties(static_spec.type_id)["value"]
        second = registry.normalize_properties(static_spec.type_id, {})["value"]
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertIsNot(first, declared_default)
        self.assertIsNot(first.payload, second.payload)
        self.assertIsNot(first.payload, declared_default.payload)
        first.payload["nested"].append(3)
        self.assertEqual(second.payload, {"nested": [1, 2]})
        self.assertEqual(declared_default.payload, {"nested": [1, 2]})

        supplied = TypedInlineValue(
            inline_type_id,
            1,
            {"nested": [7]},
        )
        normalized_supplied = registry.normalize_property_value(
            static_spec.type_id,
            "value",
            supplied,
        )
        self.assertEqual(normalized_supplied, supplied)
        self.assertIsNot(normalized_supplied, supplied)
        self.assertIsNot(normalized_supplied.payload, supplied.payload)

        dynamic_group = DynamicPortGroupSpec(
            "outputs",
            "value",
            "out",
            lambda _properties: (
                PortSpec("dynamic", "out", "data", GRAPH_DATA_TYPE_ID),
            ),
            _dynamic_key_factory,
            minimum=1,
            maximum=1,
        )
        dynamic_spec = replace(
            static_spec,
            type_id="tests.registry.typed_dynamic",
            properties=(replace(typed_property, inspector_visible=False),),
            dynamic_port_groups=(dynamic_group,),
        )
        registry.register_descriptor(dynamic_spec, _factory(dynamic_spec))
        with self.assertRaises(ValueError):
            resolve_instance_ports(dynamic_spec, {})
        self.assertEqual(
            [
                port.key
                for port in resolve_instance_ports(
                    dynamic_spec,
                    {},
                    data_types=registry.data_types,
                )
            ],
            ["result", "dynamic"],
        )

    def test_exact_typed_inline_property_defaults_validate_as_carriers(self) -> None:
        inline_type_id = "tests.registry.TypedDefault"
        other_type_id = "tests.registry.OtherTypedDefault"
        registry = NodeRegistry()
        registry.data_types.register_many(
            types=tuple(
                DataTypeSpec(
                    type_id,
                    type_id.rsplit(".", 1)[-1],
                    "graph",
                    lambda value: (
                        type(value) is dict
                        and len(value) == 1
                        and tuple(value) == ("value",)
                        and type(value["value"]) is int
                    ),
                    parents=(GRAPH_DATA_TYPE_ID,),
                    carriers=frozenset({"inline"}),
                    persistence="inline",
                )
                for type_id in (inline_type_id, other_type_id)
            ),
            owner_id="tests.registry_typed_defaults",
        )

        declared_default = TypedInlineValue(
            inline_type_id,
            1,
            {"value": 7},
        )
        port = PortSpec(
            "value",
            "in",
            "data",
            inline_type_id,
            required=True,
            uses_property_default=True,
        )

        def spec(
            type_id: str,
            default: TypedInlineValue,
            persistence_type_id: str,
        ) -> NodeTypeSpec:
            return NodeTypeSpec(
                type_id,
                type_id,
                ("Tests",),
                "",
                (port,),
                (
                    PropertySpec(
                        "value",
                        "json",
                        default,
                        "Value",
                        persistence_data_type_id=persistence_type_id,
                    ),
                ),
            )

        valid = spec(
            "tests.registry.typed_default_valid",
            declared_default,
            inline_type_id,
        )
        registry.register_descriptor(valid, _factory(valid))
        normalized = registry.default_properties(valid.type_id)["value"]
        self.assertEqual(normalized, declared_default)
        self.assertIs(type(normalized), TypedInlineValue)
        self.assertIsNot(normalized, declared_default)

        class TypedInlineSubclass(TypedInlineValue):
            pass

        invalid_defaults = (
            (
                "wrong_identity",
                TypedInlineValue(other_type_id, 1, {"value": 7}),
                other_type_id,
                ValueError,
            ),
            (
                "wrong_schema",
                TypedInlineValue(inline_type_id, 2, {"value": 7}),
                inline_type_id,
                ValueError,
            ),
            (
                "wrong_payload",
                TypedInlineValue(inline_type_id, 1, {"value": "7"}),
                inline_type_id,
                ValueError,
            ),
            (
                "subclass",
                TypedInlineSubclass(inline_type_id, 1, {"value": 7}),
                inline_type_id,
                TypeError,
            ),
        )
        for suffix, default, persistence_type_id, error_type in invalid_defaults:
            invalid = spec(
                f"tests.registry.typed_default_{suffix}",
                default,
                persistence_type_id,
            )
            with self.subTest(suffix=suffix), self.assertRaises(error_type):
                registry.register_descriptor(invalid, _factory(invalid))

    def test_dynamic_resolver_failure_keeps_complete_registry_identity_unchanged(
        self,
    ) -> None:
        registry = NodeRegistry()
        retained = NodeTypeSpec(
            "tests.dynamic.retained",
            "Retained",
            ("Tests",),
            "",
            (PortSpec("value", "out", "data", "COREX.DataTypes.Any"),),
            (),
        )
        registry.register_descriptor(retained, _factory(retained))

        def fail_resolution(_properties: Mapping[str, object]) -> tuple[PortSpec, ...]:
            raise RuntimeError("resolver failed")

        invalid = NodeTypeSpec(
            "tests.dynamic.atomic_failure",
            "Atomic Failure",
            ("Tests",),
            "",
            (),
            (
                PropertySpec(
                    "port_ids",
                    "json",
                    ["value"],
                    "Port ids",
                    inspector_visible=False,
                ),
            ),
            dynamic_port_groups=(
                DynamicPortGroupSpec(
                    "outputs",
                    "port_ids",
                    "out",
                    fail_resolution,
                    _dynamic_key_factory,
                ),
            ),
        )

        def identity() -> tuple[object, ...]:
            specs = tuple(registry.all_specs())
            return (
                tuple((spec.type_id, registry.get_entry(spec.type_id)) for spec in specs),
                registry.data_types.snapshot(),
                registry.data_types.fingerprint(),
                registry.plugin_fingerprint(),
                registry.contract_fingerprint(),
            )

        before = identity()
        with self.assertRaisesRegex(ValueError, "resolver failed"):
            registry.register_descriptor(invalid, _factory(invalid))

        self.assertEqual(identity(), before)
        self.assertIsNone(registry.spec_or_none(invalid.type_id))

    def test_dynamic_ports_cannot_use_static_readiness_declarations(self) -> None:
        spec = NodeTypeSpec(
            "tests.dynamic_readiness",
            "Dynamic Readiness",
            ("Tests",),
            "",
            (),
            (
                PropertySpec(
                    "input_ids",
                    "json",
                    ["payload"],
                    "Input ids",
                    inspector_visible=False,
                ),
            ),
            dynamic_port_groups=(
                DynamicPortGroupSpec(
                    "inputs",
                    "input_ids",
                    "in",
                    _dynamic_input_ports,
                    _dynamic_key_factory,
                    minimum=1,
                ),
            ),
            readiness_requirements=(
                ReadinessRequirementSpec(any_of_ports=("payload",)),
            ),
        )

        with self.assertRaisesRegex(ValueError, "unknown port: payload"):
            NodeRegistry().register_descriptor(spec, _factory(spec))

    def test_tabular_data_input_function_preserves_semantic_defaults(self) -> None:
        registry = build_default_registry(include_public_plugins=False)

        spec = registry.get_spec(TABULAR_DATA_INPUT_NODE_TYPE_ID)
        self.assertEqual(spec.display_name, "Tabular Data Input")
        self.assertEqual(
            {prop.key for prop in spec.properties},
            {
                "path",
                "delimiter",
                "encoding",
                "header_row",
                "skip_rows",
                "schema_hints",
                "selected_object",
                "array_slice_2d",
                "tabular_selected_columns",
                "cache_policy",
                "project_managed_source",
                "project_managed_cache",
                "allow_npz_archive_preview",
                "tabular_table_view_state",
            },
        )
        defaults = registry.default_properties(TABULAR_DATA_INPUT_NODE_TYPE_ID)
        self.assertEqual(defaults["selected_object"], "")
        self.assertEqual(defaults["cache_policy"], "app_managed_parquet")
        self.assertEqual(defaults["schema_hints"], {})
        self.assertEqual(defaults["tabular_selected_columns"], [])
        self.assertEqual(defaults["tabular_table_view_state"], {})
        self.assertEqual(
            defaults["array_slice_2d"],
            {
                "row_offset": 0,
                "column_offset": 0,
                "row_limit": 50,
                "column_limit": 50,
            },
        )

    def test_title_icon_contract_keeps_icon_authoring_field_and_descriptor_provenance(
        self,
    ) -> None:
        registry = NodeRegistry()
        spec = NodeTypeSpec(
            type_id="tests.title_icon_descriptor",
            display_name="Title Icon Descriptor",
            category_path=("Tests",),
            icon="icons/title.svg",
            ports=(
                PortSpec(
                    "value", "out", "data", "COREX.DataTypes.Any"
                ),
            ),
            properties=(),
        )
        provenance = PluginProvenance(
            kind="file",
            source_path=Path("C:/packet/tests/plugin.py"),
        )

        registry.register_descriptor(
            PluginDescriptor(
                spec=spec,
                factory=_factory(spec),
                provenance=provenance,
            )
        )

        descriptor = registry.get_descriptor(spec.type_id)
        self.assertEqual(registry.get_spec(spec.type_id).icon, "icons/title.svg")
        self.assertEqual(descriptor.spec.icon, "icons/title.svg")
        self.assertEqual(descriptor.provenance, provenance)

    def test_internal_registry_contracts_keep_focused_ownership(self) -> None:
        self.assertEqual(
            NodeTypeSpec.__module__,
            "ea_node_editor.nodes.node_specs",
        )
        self.assertEqual(
            DynamicPortGroupSpec.__module__,
            "ea_node_editor.nodes.node_specs",
        )
        self.assertEqual(
            NodeResult.__module__,
            "ea_node_editor.nodes.execution_context",
        )
        self.assertEqual(
            PluginDescriptor.__module__,
            "ea_node_editor.nodes.plugin_contracts",
        )
        self.assertEqual(
            PluginProvenance.__module__,
            "ea_node_editor.nodes.plugin_contracts",
        )
        for removed_name in (
            "CreationGeneratedFileSpec",
            "CreationPostCreateAction",
            "CreationPostCreateActionSpec",
            "CreationProfile",
            "CreationPropertyOverrideSpec",
            "StagedCreationGeneratedFile",
            "StagedCreationPostCreateAction",
            "StagedNodeCreation",
            "WizardInputSpec",
            "WizardInputType",
            "WizardPreviewSpec",
            "WizardSpec",
            "WizardValidationRule",
            "WizardValidationSpec",
            "ReadinessPropertyConditionSpec",
        ):
            self.assertFalse(hasattr(node_specs, removed_name))
        self.assertFalse(hasattr(NodeRegistry, "get_creation_profile"))
        self.assertFalse(hasattr(NodeRegistry, "creation_profile_or_none"))
        self.assertNotIn("creation_profile", PluginDescriptor.__dataclass_fields__)

    def test_plugin_toolchain_contract_manifest_accepts_compiled_backend_preparation(
        self,
    ) -> None:
        manifest = plugin_contracts.PluginContractManifest.from_value(
            {
                "runtime_backends": [
                    {
                        "backend_id": "tests.rust.external",
                        "display_name": "Tests Rust External",
                        "kind": "rust",
                        "adapter_module": "tests.runtime",
                        "adapter_factory": "create_backend",
                        "transport": "stdio-json",
                        "transport_revision": 1,
                        "runtime_behaviors": ["active", "compile_only"],
                        "toolchain_ids": ["tests.rust"],
                        "artifact_ids": ["tests.rust.dll"],
                        "surface_capability_ids": ["tests.viewer"],
                    }
                ],
                "toolchains": [
                    {
                        "toolchain_id": "tests.rust",
                        "display_name": "Tests Rust",
                        "kind": "rust",
                        "language": "rust",
                        "requirements": [
                            {
                                "requirement_id": "rustc",
                                "kind": "compiler",
                                "command": "rustc",
                                "version_spec": ">=1.75",
                            }
                        ],
                    }
                ],
                "artifacts": [
                    {
                        "artifact_id": "tests.rust.dll",
                        "kind": "shared_library",
                        "path": "target/release/tests_node.dll",
                        "runtime_backend_id": "tests.rust.external",
                        "toolchain_id": "tests.rust",
                    }
                ],
                "surface_capabilities": [
                    {
                        "capability_id": "tests.viewer",
                        "surface_family": "viewer",
                        "fullscreen": True,
                        "input_modes": ["pointer", "keyboard"],
                    }
                ],
            }
        )

        self.assertEqual(manifest.runtime_backends[0].kind, "rust")
        self.assertEqual(
            manifest.runtime_backends[0].runtime_behaviors, ("active", "compile_only")
        )
        self.assertEqual(manifest.toolchains[0].requirements[0].version_spec, ">=1.75")
        self.assertEqual(manifest.artifacts[0].kind, "shared_library")
        self.assertTrue(manifest.surface_capabilities[0].fullscreen)

    def test_plugin_toolchain_contract_manifest_rejects_unknown_backend_kind(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            plugin_contracts.RuntimeBackendSpec(
                backend_id="tests.bad_backend",
                display_name="Bad Backend",
                kind="gpu_magic",  # type: ignore[arg-type]
            )

    def test_default_builtin_catalog_registers_all_current_specs(self) -> None:
        registry = build_default_registry(include_public_plugins=False)
        type_ids = {spec.type_id for spec in registry.all_specs()}

        self.assertTrue({"core.trigger", "core.stream_gate"}.issubset(type_ids))
        self.assertIn("core.if", type_ids)
        self.assertTrue(
            {
                "ssh_sftp.secret",
                "ssh_sftp.host",
                "ssh_sftp.run_command",
                "ssh_sftp.run_script",
                "ssh_sftp.upload",
                "ssh_sftp.download",
            }.issubset(type_ids)
        )
        self.assertTrue(
            {
                "core.start",
                "core.end",
                "core.branch",
                "core.on_failure",
                "hpc.on_status",
            }.isdisjoint(type_ids)
        )
        self.assertTrue(
            {"hpc.submit", "hpc.monitor", "hpc.fetch_result"}.isdisjoint(type_ids)
        )
        self.assertIn("io.path_pointer", type_ids)
        self.assertTrue(set(PLOT_NODE_TYPE_IDS).issubset(type_ids))
        self.assertIn(WEB_PAGE_VIEWER_TYPE_ID, type_ids)

    def test_retired_active_hpc_module_is_removed(self) -> None:
        self.assertFalse(
            (
                Path(__file__).resolve().parents[1]
                / "ea_node_editor"
                / "nodes"
                / "builtins"
                / "hpc.py"
            ).exists()
        )

    def test_plot_builtin_descriptors_declare_variadic_series_and_standard_properties(
        self,
    ) -> None:
        self.assertEqual(len(PLOT_NODE_DESCRIPTORS), 8)
        for descriptor in PLOT_NODE_DESCRIPTORS:
            spec = descriptor.spec
            self.assertEqual(spec.category_path, ("Plot",))
            series_port = next(port for port in spec.ports if port.key == "series")
            self.assertEqual(series_port.direction, "in")
            self.assertEqual(series_port.kind, "data")
            self.assertTrue(series_port.data_type)
            self.assertFalse(series_port.allow_multiple_connections)
            self.assertEqual(series_port.data_access, "list")
            property_keys = {prop.key for prop in spec.properties}
            self.assertTrue(
                {
                    "backend",
                    "title",
                    "x_label",
                    "y_label",
                    "axis_limits",
                    "log_scales",
                    "grid",
                    "legend",
                    "render_in_canvas",
                    "archive_export_on_run",
                }.issubset(property_keys)
            )

    def test_nested_category_sdk_node_type_spec_accepts_one_level_path(self) -> None:
        spec = NodeTypeSpec(
            type_id="tests.category_one_level",
            display_name="Category One Level",
            category_path=("  Tests  ",),
            icon="",
            ports=(
                PortSpec(
                    "value", "out", "data", "COREX.DataTypes.Any"
                ),
            ),
            properties=(),
        )

        self.assertEqual(spec.category_path, ("Tests",))
        self.assertEqual(spec.category, "Tests")
        self.assertIsInstance(type(spec).category, property)
        self.assertIsNone(type(spec).category.fset)

    def test_nested_category_sdk_node_type_spec_accepts_ten_level_path(self) -> None:
        category_path = tuple(f"Level {index}" for index in range(1, 11))
        spec = NodeTypeSpec(
            type_id="tests.category_ten_level",
            display_name="Category Ten Level",
            category_path=category_path,
            icon="",
            ports=(
                PortSpec(
                    "value", "out", "data", "COREX.DataTypes.Any"
                ),
            ),
            properties=(),
        )

        self.assertEqual(spec.category_path, category_path)
        self.assertEqual(
            spec.category,
            "Level 1 > Level 2 > Level 3 > Level 4 > Level 5 > "
            "Level 6 > Level 7 > Level 8 > Level 9 > Level 10",
        )

    def test_nested_category_sdk_node_type_spec_rejects_eleven_level_path(self) -> None:
        with self.assertRaises(ValueError):
            NodeTypeSpec(
                type_id="tests.category_eleven_level",
                display_name="Category Eleven Level",
                category_path=tuple(f"Level {index}" for index in range(1, 12)),
                icon="",
                ports=(
                    PortSpec(
                        "value", "out", "data", "COREX.DataTypes.Any"
                    ),
                ),
                properties=(),
            )

    def test_nested_category_sdk_node_type_spec_rejects_empty_segments(self) -> None:
        for category_path in ((), ("",), ("  ",), ("Tests", ""), ("Tests", "  ")):
            with self.subTest(category_path=category_path):
                with self.assertRaises(ValueError):
                    NodeTypeSpec(
                        type_id="tests.category_empty_segment",
                        display_name="Category Empty Segment",
                        category_path=category_path,
                        icon="",
                        ports=(
                            PortSpec(
                                "value",
                                "out",
                                "data",
                                "COREX.DataTypes.Any",
                            ),
                        ),
                        properties=(),
                    )

    def test_explicit_text_editor_metadata_preserves_supported_editor(self) -> None:
        registry = NodeRegistry()
        spec = NodeTypeSpec(
            type_id="tests.text_editor",
            display_name="Text Editor",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec(
                    "value", "out", "data", "COREX.DataTypes.Any"
                ),
            ),
            properties=(
                PropertySpec(
                    "notes",
                    "str",
                    "Ready",
                    "Notes",
                    inline_editor="text",
                    inspector_editor="text",
                ),
                PropertySpec(
                    "font_family",
                    "str",
                    "",
                    "Font Family",
                    inspector_editor="font_family",
                ),
            ),
            runtime_behavior="passive",
            surface_family="annotation",
        )

        registry.register(_factory(spec))

        registered = registry.get_spec(spec.type_id)
        property_spec = registered.properties[0]
        self.assertEqual(node_specs.property_inspector_editor(property_spec), "text")
        self.assertEqual(
            node_specs.property_inspector_editor(registered.properties[1]),
            "font_family",
        )
        self.assertEqual(node_specs.inline_property_specs(registered), (property_spec,))
        self.assertEqual(
            node_specs.inline_property_specs(registered)[0].inline_editor, "text"
        )

    def test_sensitive_property_requires_json_secret_editor_and_enum_scope(
        self,
    ) -> None:
        registry = NodeRegistry()
        valid = NodeTypeSpec(
            type_id="tests.sensitive_property",
            display_name="Sensitive Property",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec(
                    "value", "out", "data", "COREX.DataTypes.Any"
                ),
            ),
            properties=(
                PropertySpec(
                    "scope",
                    "enum",
                    "Current user",
                    "Scope",
                    enum_values=("Current user", "All users on this machine"),
                    inline_editor="enum",
                ),
                PropertySpec(
                    "protected_value",
                    "json",
                    {},
                    "Value",
                    description="Masked value.",
                    inline_editor="secret",
                    inspector_editor="secret",
                    sensitive=True,
                    sensitive_scope_key="scope",
                ),
            ),
        )
        registry.register(_factory(valid))
        registered = registry.get_spec(valid.type_id).properties[1]
        self.assertTrue(registered.sensitive)
        self.assertEqual(registered.description, "Masked value.")

        invalid_properties = (
            replace(registered, type="str"),
            replace(registered, inline_editor="", inspector_editor=""),
            replace(registered, sensitive_scope_key="missing"),
            replace(registered, sensitive=False, sensitive_scope_key=""),
        )
        for index, invalid_property in enumerate(invalid_properties):
            with self.subTest(index=index):
                invalid_spec = replace(
                    valid,
                    type_id=f"tests.invalid_sensitive_property_{index}",
                    properties=(valid.properties[0], invalid_property),
                )
                with self.assertRaises(ValueError):
                    NodeRegistry().register(_factory(invalid_spec))

    def test_path_property_accepts_file_dialog_filter_metadata(self) -> None:
        registry = NodeRegistry()
        spec = NodeTypeSpec(
            type_id="tests.path_filter",
            display_name="Path Filter",
            category_path=("Tests",),
            icon="",
            ports=(PortSpec("value", "out", "data", "COREX.DataTypes.Path"),),
            properties=(
                PropertySpec(
                    "source_path",
                    "path",
                    "",
                    "Source Path",
                    inline_editor="path",
                    file_filter="Data Files (*.csv);;All Files (*)",
                ),
            ),
        )

        registry.register(_factory(spec))

        self.assertEqual(
            registry.get_spec(spec.type_id).properties[0].file_filter,
            "Data Files (*.csv);;All Files (*)",
        )

    def test_file_dialog_filter_requires_path_property_or_editor(self) -> None:
        registry = NodeRegistry()
        spec = NodeTypeSpec(
            type_id="tests.invalid_file_filter",
            display_name="Invalid File Filter",
            category_path=("Tests",),
            icon="",
            ports=(PortSpec("value", "out", "data", "COREX.DataTypes.String"),),
            properties=(
                PropertySpec(
                    "message",
                    "str",
                    "",
                    "Message",
                    file_filter="Text Files (*.txt);;All Files (*)",
                ),
            ),
        )

        with self.assertRaises(ValueError):
            registry.register(_factory(spec))

    def test_slider_inline_editor_accepts_numeric_range_metadata(self) -> None:
        registry = NodeRegistry()
        spec = NodeTypeSpec(
            type_id="tests.slider_editor",
            display_name="Slider Editor",
            category_path=("Tests",),
            icon="",
            ports=(PortSpec("value", "out", "data", "COREX.DataTypes.Double"),),
            properties=(
                PropertySpec(
                    "ratio",
                    "float",
                    0.5,
                    "Ratio",
                    inline_editor="slider",
                    minimum=0.0,
                    maximum=1.0,
                    step=0.05,
                ),
            ),
        )

        registry.register(_factory(spec))

        registered = registry.get_spec(spec.type_id).properties[0]
        self.assertEqual(registered.inline_editor, "slider")
        self.assertEqual(registered.minimum, 0.0)
        self.assertEqual(registered.maximum, 1.0)
        self.assertEqual(registered.step, 0.05)

    def test_slider_inline_editor_rejects_invalid_type_or_range(self) -> None:
        invalid_property_cases = (
            {"type": "str", "default": "x", "minimum": 0.0, "maximum": 1.0},
            {"type": "float", "default": 0.5, "minimum": None, "maximum": 1.0},
            {"type": "float", "default": 0.5, "minimum": 0.0, "maximum": None},
            {"type": "float", "default": 0.5, "minimum": 1.0, "maximum": 1.0},
            {"type": "int", "default": 2, "minimum": 5.0, "maximum": 1.0},
            {
                "type": "float",
                "default": 0.5,
                "minimum": 0.0,
                "maximum": 1.0,
                "step": -0.5,
            },
        )
        for case_index, case in enumerate(invalid_property_cases):
            registry = NodeRegistry()
            spec = NodeTypeSpec(
                type_id=f"tests.invalid_slider_{case_index}",
                display_name="Invalid Slider",
                category_path=("Tests",),
                icon="",
                ports=(
                    PortSpec(
                        "value", "out", "data", "COREX.DataTypes.Any"
                    ),
                ),
                properties=(
                    PropertySpec(
                        "amount",
                        case["type"],
                        case["default"],
                        "Amount",
                        inline_editor="slider",
                        minimum=case["minimum"],
                        maximum=case["maximum"],
                        step=case.get("step", 0.0),
                    ),
                ),
            )
            with self.assertRaises(
                ValueError, msg=f"case {case_index} should be rejected"
            ):
                registry.register(_factory(spec))

    def test_registry_accepts_interval_searchable_enum_and_property_condition_contracts(
        self,
    ) -> None:
        condition = PropertyConditionSpec("mode", ("Manual", "Manual"))
        increasing = replace(
            prop_interval_1d(
                "increasing",
                Interval1D(0.3, 0.7),
                "Increasing",
                minimum=0.0,
                maximum=1.0,
                step=0.2,
            ),
            default=serialize_runtime_value(Interval1D(0.3, 0.7)),
        )
        decreasing = prop_interval_1d(
            "decreasing",
            Interval1D(10.0, 0.0),
            "Decreasing",
            minimum=0.0,
            maximum=100.0,
            direction="decreasing",
        )
        equal_increasing = prop_interval_1d(
            "equal_increasing",
            Interval1D(5.0, 5.0),
            "Equal increasing",
            minimum=0.0,
            maximum=10.0,
        )
        equal_decreasing = prop_interval_1d(
            "equal_decreasing",
            Interval1D(5.0, 5.0),
            "Equal decreasing",
            minimum=0.0,
            maximum=10.0,
            direction="decreasing",
        )
        spec = NodeTypeSpec(
            type_id="tests.interval_property_contract",
            display_name="Interval Property Contract",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec(
                    "increasing",
                    "in",
                    "data",
                    "COREX.DataTypes.Interval1D",
                    required=False,
                    uses_property_default=True,
                ),
                PortSpec("result", "out", "data", "COREX.DataTypes.Interval1D"),
            ),
            properties=(
                prop_enum(
                    "mode",
                    "None",
                    "Mode",
                    values=("None", "Manual"),
                    inline_editor="enum",
                    searchable=True,
                ),
                prop_int(
                    "sectors",
                    2,
                    "Sectors",
                    minimum=2,
                    maximum=360,
                    inline_editor="slider",
                    enabled_when=condition,
                ),
                increasing,
                decreasing,
                equal_increasing,
                equal_decreasing,
            ),
        )
        registry = NodeRegistry()

        registry.register_descriptor(spec, _factory(spec))

        registered = registry.get_spec(spec.type_id)
        self.assertTrue(registered.properties[0].searchable)
        self.assertEqual(registered.properties[1].enabled_when, condition)
        defaults = registry.default_properties(spec.type_id)
        self.assertEqual(defaults["increasing"], Interval1D(0.3, 0.7))
        self.assertEqual(defaults["decreasing"], Interval1D(10.0, 0.0))
        self.assertEqual(defaults["equal_increasing"], Interval1D(5.0, 5.0))
        self.assertEqual(defaults["equal_decreasing"], Interval1D(5.0, 5.0))
        self.assertEqual(
            registry.normalize_property_value(
                spec.type_id,
                "decreasing",
                serialize_runtime_value(Interval1D(9.0, 1.0)),
            ),
            Interval1D(9.0, 1.0),
        )
        self.assertEqual(
            registry.normalize_property_value(spec.type_id, "decreasing", [9.0, 1.0]),
            Interval1D(10.0, 0.0),
        )
        self.assertEqual(
            increasing.persistence_data_type_id,
            INTERVAL_1D_GRAPH_DATA_TYPE_ID,
        )

    def test_property_persistence_opt_in_requires_catalog_persistent_type(self) -> None:
        base = NodeTypeSpec(
            "tests.property_persistence",
            "Property Persistence",
            ("Tests",),
            "",
            (PortSpec("result", "out", "data", GRAPH_DATA_TYPE_ID),),
            (
                PropertySpec(
                    "value",
                    "json",
                    {},
                    "Value",
                    persistence_data_type_id="Packet.Unknown",
                ),
            ),
        )

        with self.assertRaisesRegex(
            ValueError, "unknown data-type ID 'Packet.Unknown'"
        ):
            NodeRegistry().register_descriptor(base, _factory(base))

        never = replace(
            base,
            properties=(
                replace(
                    base.properties[0],
                    persistence_data_type_id=GRAPH_DATA_TYPE_ID,
                ),
            ),
        )
        with self.assertRaisesRegex(ValueError, "does not permit persistence"):
            NodeRegistry().register_descriptor(never, _factory(never))

    def test_registry_rejects_invalid_property_conditions(self) -> None:
        base_properties = (
            prop_enum(
                "mode",
                "None",
                "Mode",
                values=("None", "Manual"),
                inline_editor="enum",
            ),
            PropertySpec("count", "int", 2, "Count"),
            PropertySpec("ratio", "float", 0.5, "Ratio"),
            PropertySpec("payload", "json", {}, "Payload"),
            PropertySpec("bounds", "interval_1d", Interval1D(0, 1), "Bounds"),
            PropertySpec("target", "int", 1, "Target"),
        )
        invalid_conditions = (
            PropertyConditionSpec("missing", ("Manual",)),
            PropertyConditionSpec("target", (1,)),
            PropertyConditionSpec("payload", ({},)),
            PropertyConditionSpec("bounds", (Interval1D(0, 1),)),
            PropertyConditionSpec("mode"),
            PropertyConditionSpec("mode", ["Manual"]),  # type: ignore[arg-type]
            PropertyConditionSpec("count", ("2",)),
            PropertyConditionSpec("ratio", (1,)),
            PropertyConditionSpec("mode", ("Automatic",)),
        )
        for case_index, condition in enumerate(invalid_conditions):
            properties = (
                *base_properties[:-1],
                replace(base_properties[-1], enabled_when=condition),
            )
            spec = NodeTypeSpec(
                type_id=f"tests.invalid_property_condition_{case_index}",
                display_name="Invalid Property Condition",
                category_path=("Tests",),
                icon="",
                ports=(
                    PortSpec("result", "out", "data", "COREX.DataTypes.Int"),
                ),
                properties=properties,
            )
            with (
                self.subTest(case=case_index),
                self.assertRaises((TypeError, ValueError)),
            ):
                NodeRegistry().register_descriptor(spec, _factory(spec))

    def test_registry_rejects_invalid_searchable_property_contracts(self) -> None:
        invalid_properties = (
            PropertySpec(
                "value", "str", "x", "Value", inline_editor="enum", searchable=True
            ),
            PropertySpec(
                "value", "int", 1, "Value", inline_editor="number", searchable=True
            ),
            replace(
                prop_interval_1d(
                    "value",
                    Interval1D(0.0, 1.0),
                    "Value",
                    minimum=0.0,
                    maximum=10.0,
                ),
                searchable=True,
            ),
            PropertySpec(
                "value",
                "enum",
                "x",
                "Value",
                enum_values=("x", "y"),
                searchable=True,
            ),
            PropertySpec(
                "value",
                "enum",
                "x",
                "Value",
                enum_values=("x", "y"),
                inline_editor="text",
                searchable=True,
            ),
            PropertySpec(
                "value",
                "enum",
                "x",
                "Value",
                enum_values=("x", "y"),
                inline_editor="enum",
                searchable=1,  # type: ignore[arg-type]
            ),
        )
        for case_index, prop in enumerate(invalid_properties):
            spec = NodeTypeSpec(
                type_id=f"tests.invalid_searchable_{case_index}",
                display_name="Invalid Searchable",
                category_path=("Tests",),
                icon="",
                ports=(
                    PortSpec("result", "out", "data", "COREX.DataTypes.String"),
                ),
                properties=(prop,),
            )
            with (
                self.subTest(case=case_index),
                self.assertRaises((TypeError, ValueError)),
            ):
                NodeRegistry().register_descriptor(spec, _factory(spec))

    def test_registry_rejects_invalid_interval_property_contracts(self) -> None:
        base = prop_interval_1d(
            "bounds",
            Interval1D(0.0, 1.0),
            "Bounds",
            minimum=0.0,
            maximum=10.0,
            step=0.001,
        )
        invalid_properties = (
            replace(base, default=Interval1D(10.0, 0.0)),
            replace(
                base, default=Interval1D(0.0, 10.0), interval_direction="decreasing"
            ),
            replace(base, default=Interval1D(-1.0, 1.0)),
            replace(base, default=[0.0, 1.0]),
            replace(base, default=(0.0, 1.0)),
            replace(base, default={"start": 0.0, "end": 1.0}),
            replace(
                base, default={"__ea_runtime_value__": "interval_1d", "start": 0.0}
            ),
            replace(
                base,
                default={
                    "__ea_runtime_value__": "interval_1d",
                    "start": float("nan"),
                    "end": 1.0,
                },
            ),
            replace(base, minimum=1.0, maximum=1.0),
            replace(base, maximum=float("inf")),
            replace(base, step=-0.1),
            replace(base, step=float("nan")),
            replace(base, interval_direction="sideways"),  # type: ignore[arg-type]
            PropertySpec(
                "bounds",
                "float",
                0.5,
                "Bounds",
                interval_direction="increasing",
            ),
            PropertySpec(
                "bounds",
                "float",
                0.5,
                "Bounds",
                inline_editor="interval_slider",
                minimum=0.0,
                maximum=1.0,
                interval_direction="increasing",
            ),
            replace(base, inline_editor="slider"),
        )
        for case_index, prop in enumerate(invalid_properties):
            spec = NodeTypeSpec(
                type_id=f"tests.invalid_interval_property_{case_index}",
                display_name="Invalid Interval Property",
                category_path=("Tests",),
                icon="",
                ports=(
                    PortSpec("result", "out", "data", "COREX.DataTypes.Interval1D"),
                ),
                properties=(prop,),
            )
            with (
                self.subTest(case=case_index),
                self.assertRaises((TypeError, ValueError)),
            ):
                NodeRegistry().register_descriptor(spec, _factory(spec))

    def test_untagged_string_properties_still_resolve_to_text_editor(self) -> None:
        property_spec = PropertySpec(
            "accent_color",
            "str",
            "#336699",
            "Accent Color",
        )
        spec = NodeTypeSpec(
            type_id="tests.untyped_color_text",
            display_name="Untagged Color Text",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec(
                    "value", "out", "data", "COREX.DataTypes.Any"
                ),
            ),
            properties=(property_spec,),
        )

        self.assertEqual(node_specs.property_inspector_editor(property_spec), "text")
        self.assertEqual(node_specs.inline_property_specs(spec), ())

    def test_register_rejects_invalid_surface_family(self) -> None:
        registry = NodeRegistry()
        spec = NodeTypeSpec(
            type_id="tests.bad_surface",
            display_name="Bad Surface",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec(
                    "value", "out", "data", "COREX.DataTypes.Any"
                ),
            ),
            properties=(),
            runtime_behavior="passive",
            surface_family="diagram",  # type: ignore[arg-type]
        )
        with self.assertRaises(ValueError):
            registry.register(_factory(spec))

    def test_register_accepts_neutral_flowchart_ports_with_matching_cardinal_side(
        self,
    ) -> None:
        registry = NodeRegistry()
        spec = NodeTypeSpec(
            type_id="tests.neutral_flowchart",
            display_name="Neutral Flowchart",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec(
                    "top",
                    "neutral",
                    "flow",
                    "flow",
                    side="top",
                    allow_multiple_connections=True,
                ),
                PortSpec(
                    "right",
                    "neutral",
                    "flow",
                    "flow",
                    side="right",
                    allow_multiple_connections=True,
                ),
            ),
            properties=(),
            runtime_behavior="passive",
            surface_family="flowchart",
            surface_variant="process",
        )

        registry.register(_factory(spec))

        registered = registry.get_spec("tests.neutral_flowchart")
        self.assertEqual(
            tuple(port.direction for port in registered.ports), ("neutral", "neutral")
        )
        self.assertEqual(
            tuple(port.side for port in registered.ports), ("top", "right")
        )

    def test_register_accepts_neutral_ports_on_passive_non_flowchart_nodes(
        self,
    ) -> None:
        registry = NodeRegistry()
        spec = NodeTypeSpec(
            type_id="tests.passive_neutral_annotation",
            display_name="Passive Neutral Annotation",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec(
                    "top",
                    "neutral",
                    "flow",
                    "flow",
                    side="top",
                    allow_multiple_connections=True,
                ),
            ),
            properties=(),
            runtime_behavior="passive",
            surface_family="annotation",
        )

        registry.register(_factory(spec))

        registered = registry.get_spec(spec.type_id)
        self.assertEqual(
            tuple(port.direction for port in registered.ports), ("neutral",)
        )
        self.assertEqual(tuple(port.side for port in registered.ports), ("top",))

    def test_register_rejects_neutral_ports_on_active_nodes(self) -> None:
        registry = NodeRegistry()
        spec = NodeTypeSpec(
            type_id="tests.bad_neutral_active",
            display_name="Bad Neutral Active",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec(
                    "top",
                    "neutral",
                    "flow",
                    "flow",
                    side="top",
                    allow_multiple_connections=True,
                ),
            ),
            properties=(),
            surface_family="standard",
        )

        with self.assertRaises(ValueError):
            registry.register(_factory(spec))

    def test_register_rejects_neutral_ports_without_matching_cardinal_key(self) -> None:
        registry = NodeRegistry()
        spec = NodeTypeSpec(
            type_id="tests.bad_neutral_side",
            display_name="Bad Neutral Side",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec(
                    "branch",
                    "neutral",
                    "flow",
                    "flow",
                    side="right",
                    allow_multiple_connections=True,
                ),
            ),
            properties=(),
            surface_family="flowchart",
            surface_variant="decision",
        )

        with self.assertRaises(ValueError):
            registry.register(_factory(spec))

    def test_node_type_spec_defaults_render_quality_contract(self) -> None:
        spec = NodeTypeSpec(
            type_id="tests.render_quality_defaults",
            display_name="Render Quality Defaults",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec(
                    "value", "out", "data", "COREX.DataTypes.Any"
                ),
            ),
            properties=(),
        )

        self.assertEqual(spec.render_quality, NodeRenderQualitySpec())
        self.assertEqual(spec.render_quality.supported_quality_tiers, ("full",))

    def test_decorator_authored_nodes_publish_normalized_render_quality_contract(
        self,
    ) -> None:
        registry = NodeRegistry()

        @node_type(
            type_id="tests.decorated_render_quality",
            display_name="Decorated Render Quality",
            category_path=("Tests",),
            icon="",
            ports=(),
            properties=(),
            render_quality={
                "supported_quality_tiers": ["full", "proxy", "proxy"],
            },
        )
        class _DecoratedRenderQualityNode:
            def execute(self, _ctx) -> NodeResult:  # noqa: ANN001
                return NodeResult()

        registry.register(lambda: _DecoratedRenderQualityNode())

        spec = registry.get_spec("tests.decorated_render_quality")
        self.assertEqual(spec.render_quality.supported_quality_tiers, ("full", "proxy"))

    def test_render_quality_rejects_invalid_tier(self) -> None:
        with self.assertRaises(ValueError):
            NodeTypeSpec(
                type_id="tests.bad_render_quality",
                display_name="Bad Render Quality",
                category_path=("Tests",),
                icon="",
                ports=(
                    PortSpec(
                        "value", "out", "data", "COREX.DataTypes.Any"
                    ),
                ),
                properties=(),
                render_quality={"supported_quality_tiers": ("full", "ultra")},  # type: ignore[arg-type]
            )

    def test_normalize_project_for_registry_marks_same_count_workspace_changes(
        self,
    ) -> None:
        registry = NodeRegistry()
        spec = NodeTypeSpec(
            type_id="tests.normalize_epoch",
            display_name="Normalize Epoch",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec(
                    "value", "out", "data", "COREX.DataTypes.Any"
                ),
            ),
            properties=(PropertySpec("count", "int", 7, "Count"),),
        )
        registry.register(_factory(spec))
        model = GraphModel()
        workspace = model.active_workspace
        node = NodeInstance(
            node_id="node_normalize_epoch",
            type_id="tests.normalize_epoch",
            title="Normalize Epoch",
            x=0.0,
            y=0.0,
            properties={"count": "15", "stale": "drop"},
            exposed_ports={"stale_port": True},
        )
        workspace.nodes[node.node_id] = node
        revision_before = workspace.mutation_revision
        epoch_before = model.project.document_epoch()

        normalize_project_for_registry(model.project, registry)

        self.assertEqual(node.properties, {"count": 15})
        self.assertEqual(node.exposed_ports, {"value": True})
        self.assertTrue(workspace.dirty)
        self.assertGreater(workspace.mutation_revision, revision_before)
        self.assertNotEqual(model.project.document_epoch(), epoch_before)

        revision_after = workspace.mutation_revision
        epoch_after = model.project.document_epoch()
        normalize_project_for_registry(model.project, registry)

        self.assertEqual(workspace.mutation_revision, revision_after)
        self.assertEqual(model.project.document_epoch(), epoch_after)

    def test_normalize_project_for_registry_prunes_unknown_nodes_without_sidecars(
        self,
    ) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace

        known_source = model.add_node(
            workspace.workspace_id, "core.constant", "Source", 0.0, 0.0
        )
        known_target = model.add_node(
            workspace.workspace_id, "core.logger", "Target", 320.0, 0.0
        )
        unknown_node = NodeInstance(
            node_id="node_unknown",
            type_id="plugin.missing_step",
            title="Missing Step",
            x=160.0,
            y=0.0,
            collapsed=True,
            properties={"threshold": 0.5},
            exposed_ports={"plugin_in": True},
            visual_style={"fill": "#556677"},
        )
        workspace.nodes[unknown_node.node_id] = unknown_node
        child_node = model.add_node(
            workspace.workspace_id, "core.logger", "Child", 200.0, 80.0
        )
        child_node.parent_node_id = unknown_node.node_id

        valid_edge = model.add_edge(
            workspace.workspace_id,
            known_source.node_id,
            "as_text",
            known_target.node_id,
            "message",
        )
        mixed_edge = model.add_edge(
            workspace.workspace_id,
            unknown_node.node_id,
            "plugin_out",
            known_target.node_id,
            "message",
        )

        normalize_project_for_registry(model.project, registry)

        self.assertNotIn(unknown_node.node_id, workspace.nodes)
        self.assertIsNone(workspace.nodes[child_node.node_id].parent_node_id)
        self.assertEqual(set(workspace.edges), {valid_edge.edge_id})
        self.assertNotIn(mixed_edge.edge_id, workspace.edges)

    def test_normalize_project_for_registry_prunes_missing_addon(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        addon_node = NodeInstance(
            node_id="node_signal_transform",
            type_id="addons.signal.transform",
            title="Signal Transform",
            x=120.0,
            y=40.0,
            collapsed=True,
            properties={"gain": 2.0},
            exposed_ports={"signal_in": True, "signal_out": True},
            visual_style={"fill": "#225588"},
        )
        workspace.nodes[addon_node.node_id] = addon_node

        normalize_project_for_registry(model.project, registry)

        self.assertNotIn(addon_node.node_id, workspace.nodes)

    def test_normalize_project_for_registry_keeps_directed_neutral_flowchart_edges(
        self,
    ) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        source = model.add_node(
            workspace.workspace_id, "passive.flowchart.process", "Process", 20.0, 30.0
        )
        target = model.add_node(
            workspace.workspace_id, "passive.flowchart.process", "Process", 320.0, 30.0
        )
        edge = model.add_edge(
            workspace.workspace_id,
            source.node_id,
            "right",
            target.node_id,
            "left",
        )

        normalize_project_for_registry(model.project, registry)

        self.assertIn(edge.edge_id, workspace.edges)
        kept_edge = workspace.edges[edge.edge_id]
        self.assertEqual(kept_edge.source_port_key, "right")
        self.assertEqual(kept_edge.target_port_key, "left")

    def test_default_registry_preserves_promoted_subnode_contract(self) -> None:
        registry = build_default_registry()

        shell_spec = registry.get_spec(SUBNODE_TYPE_ID)
        input_spec = registry.get_spec(SUBNODE_INPUT_TYPE_ID)
        output_spec = registry.get_spec(SUBNODE_OUTPUT_TYPE_ID)

        self.assertEqual(shell_spec.type_id, SUBNODE_TYPE_ID)
        self.assertEqual(input_spec.type_id, SUBNODE_INPUT_TYPE_ID)
        self.assertEqual(output_spec.type_id, SUBNODE_OUTPUT_TYPE_ID)
        self.assertEqual(input_spec.ports[0].key, SUBNODE_PIN_PORT_KEY)
        self.assertEqual(output_spec.ports[0].key, SUBNODE_PIN_PORT_KEY)

        list_input = resolve_subnode_pin_definition(
            SUBNODE_INPUT_TYPE_ID,
            {
                "label": "Values",
                "kind": "data",
                "data_type": STRING_DATA_TYPE_ID,
                SUBNODE_PIN_ACCEPTED_DATA_TYPES_PROPERTY: [
                    INTEGER_DATA_TYPE_ID,
                ],
                "data_access": "list",
            },
        )
        data_output = resolve_subnode_pin_definition(
            SUBNODE_OUTPUT_TYPE_ID,
            {
                "label": "Result",
                "kind": "data",
                "data_type": DOUBLE_DATA_TYPE_ID,
                "data_access": "tree",
            },
        )

        self.assertEqual(default_subnode_pin_label(SUBNODE_INPUT_TYPE_ID), "Input")
        self.assertEqual(default_subnode_pin_label(SUBNODE_OUTPUT_TYPE_ID), "Output")
        self.assertEqual(list_input.label, "Values")
        self.assertEqual(list_input.pin_port_direction, "out")
        self.assertEqual(list_input.shell_port_direction, "in")
        self.assertEqual(list_input.kind, "data")
        self.assertEqual(list_input.data_type, STRING_DATA_TYPE_ID)
        self.assertEqual(
            list_input.accepted_data_types,
            (INTEGER_DATA_TYPE_ID,),
        )
        self.assertEqual(list_input.data_access, "list")
        self.assertEqual(data_output.label, "Result")
        self.assertEqual(data_output.pin_port_direction, "in")
        self.assertEqual(data_output.shell_port_direction, "out")
        self.assertEqual(data_output.kind, "data")
        self.assertEqual(data_output.data_type, DOUBLE_DATA_TYPE_ID)
        self.assertEqual(data_output.data_access, "tree")

    def test_grouping_preserves_canonical_input_type_union(self) -> None:
        registry = build_default_registry()
        typed_spec = NodeTypeSpec(
            type_id="tests.grouping.typed_input",
            display_name="Typed Input",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec(
                    "value",
                    "in",
                    "data",
                    STRING_DATA_TYPE_ID,
                    required=True,
                    accepted_data_types=(INTEGER_DATA_TYPE_ID,),
                ),
            ),
            properties=(),
        )
        registry.register_descriptor(typed_spec, _factory(typed_spec))
        model = GraphModel()
        workspace = model.active_workspace
        mutations = model.validated_mutations(workspace.workspace_id, registry)
        external = mutations.add_node(
            type_id="core.constant",
            title="External",
            x=0.0,
            y=0.0,
        )
        grouped_target = mutations.add_node(
            type_id=typed_spec.type_id,
            title="Typed",
            x=260.0,
            y=0.0,
        )
        filler = mutations.add_node(
            type_id="core.constant",
            title="Filler",
            x=260.0,
            y=120.0,
        )
        mutations.add_edge(
            source_node_id=external.node_id,
            source_port_key="value",
            target_node_id=grouped_target.node_id,
            target_port_key="value",
        )

        grouped = group_selection_into_subnode(
            model=model,
            registry=registry,
            workspace_id=workspace.workspace_id,
            selected_node_ids=[grouped_target.node_id, filler.node_id],
            scope_path=[],
            shell_x=220.0,
            shell_y=40.0,
        )

        self.assertIsNotNone(grouped)
        assert grouped is not None
        input_pin = next(
            workspace.nodes[node_id]
            for node_id in grouped.created_pin_node_ids
            if workspace.nodes[node_id].type_id == SUBNODE_INPUT_TYPE_ID
        )
        pin_definition = resolve_subnode_pin_definition(
            input_pin.type_id,
            input_pin.properties,
        )
        self.assertEqual(pin_definition.data_type, STRING_DATA_TYPE_ID)
        self.assertEqual(
            pin_definition.accepted_data_types,
            (INTEGER_DATA_TYPE_ID,),
        )

    def test_validated_mutation_service_round_trips_subnode_grouping_through_split_ops(
        self,
    ) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        mutations = model.validated_mutations(workspace.workspace_id, registry)

        source = mutations.add_node(
            type_id="core.constant", title="Source", x=0.0, y=0.0
        )
        script = mutations.add_node(
            type_id="core.python_script", title="Script", x=220.0, y=0.0
        )
        sink = mutations.add_node(type_id="core.logger", title="Sink", x=520.0, y=0.0)
        mutations.set_exposed_port(sink.node_id, "message", True)

        mutations.add_edge(
            source_node_id=source.node_id,
            source_port_key="value",
            target_node_id=script.node_id,
            target_port_key="payload",
        )
        outgoing = mutations.add_edge(
            source_node_id=script.node_id,
            source_port_key="result",
            target_node_id=sink.node_id,
            target_port_key="message",
        )
        mutations.set_edge_enabled(outgoing.edge_id, False)

        grouped = group_selection_into_subnode(
            model=model,
            registry=registry,
            workspace_id=workspace.workspace_id,
            selected_node_ids=[source.node_id, script.node_id],
            scope_path=[],
            shell_x=140.0,
            shell_y=40.0,
        )

        self.assertIsNotNone(grouped)
        assert grouped is not None
        self.assertEqual(
            workspace.nodes[grouped.shell_node_id].type_id, SUBNODE_TYPE_ID
        )
        self.assertEqual(
            workspace.nodes[source.node_id].parent_node_id, grouped.shell_node_id
        )
        self.assertEqual(
            workspace.nodes[script.node_id].parent_node_id, grouped.shell_node_id
        )
        self.assertEqual(len(grouped.created_pin_node_ids), 1)
        pin = workspace.nodes[grouped.created_pin_node_ids[0]]
        self.assertEqual(
            resolve_subnode_pin_definition(pin.type_id, pin.properties).data_access,
            "item",
        )
        self.assertTrue(
            any(
                edge.source_node_id == grouped.shell_node_id
                and edge.target_node_id == sink.node_id
                and edge.target_port_key == "message"
                and not edge.enabled
                for edge in workspace.edges.values()
            )
        )

        ungrouped = ungroup_subnode(
            model=model,
            workspace_id=workspace.workspace_id,
            shell_node_id=grouped.shell_node_id,
        )

        self.assertIsNotNone(ungrouped)
        assert ungrouped is not None
        self.assertEqual(ungrouped.removed_shell_node_id, grouped.shell_node_id)
        self.assertCountEqual(
            ungrouped.removed_pin_node_ids, grouped.created_pin_node_ids
        )
        self.assertNotIn(grouped.shell_node_id, workspace.nodes)
        self.assertIsNone(workspace.nodes[source.node_id].parent_node_id)
        self.assertIsNone(workspace.nodes[script.node_id].parent_node_id)
        self.assertTrue(
            any(
                edge.source_node_id == source.node_id
                and edge.source_port_key == "value"
                and edge.target_node_id == script.node_id
                and edge.target_port_key == "payload"
                for edge in workspace.edges.values()
            )
        )
        self.assertTrue(
            any(
                edge.source_node_id == script.node_id
                and edge.source_port_key == "result"
                and edge.target_node_id == sink.node_id
                and edge.target_port_key == "message"
                and not edge.enabled
                for edge in workspace.edges.values()
            )
        )

    def test_graph_fragment_insert_remaps_subnode_shell_pin_port_keys(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        mutations = model.validated_mutations(workspace.workspace_id, registry)

        source = mutations.add_node(
            type_id="core.constant", title="Source", x=0.0, y=0.0
        )
        script = mutations.add_node(
            type_id="core.python_script", title="Script", x=220.0, y=0.0
        )
        sink = mutations.add_node(type_id="core.logger", title="Sink", x=520.0, y=0.0)
        mutations.set_exposed_port(sink.node_id, "message", True)
        mutations.add_edge(
            source_node_id=source.node_id,
            source_port_key="value",
            target_node_id=script.node_id,
            target_port_key="payload",
        )
        mutations.add_edge(
            source_node_id=script.node_id,
            source_port_key="result",
            target_node_id=sink.node_id,
            target_port_key="message",
        )
        grouped = group_selection_into_subnode(
            model=model,
            registry=registry,
            workspace_id=workspace.workspace_id,
            selected_node_ids=[source.node_id, script.node_id],
            scope_path=[],
            shell_x=140.0,
            shell_y=40.0,
        )
        self.assertIsNotNone(grouped)
        assert grouped is not None
        original_pin_id = grouped.created_pin_node_ids[0]
        fragment_data = build_subtree_fragment_payload_data(
            workspace=workspace,
            selected_node_ids=[grouped.shell_node_id, sink.node_id],
        )
        self.assertIsNotNone(fragment_data)
        assert fragment_data is not None
        fragment_payload = build_graph_fragment_payload(
            nodes=fragment_data["nodes"], edges=fragment_data["edges"]
        )

        before_node_ids = set(workspace.nodes)
        inserted_node_ids = insert_graph_fragment(
            model=model,
            workspace_id=workspace.workspace_id,
            fragment_payload=fragment_payload,
            delta_x=800.0,
            delta_y=0.0,
        )

        self.assertTrue(inserted_node_ids)
        inserted_node_id_set = set(inserted_node_ids)
        self.assertTrue(inserted_node_id_set.isdisjoint(before_node_ids))
        inserted_shell_id = next(
            node_id
            for node_id in inserted_node_id_set
            if workspace.nodes[node_id].type_id == SUBNODE_TYPE_ID
        )
        inserted_pin_id = next(
            node_id
            for node_id in inserted_node_id_set
            if workspace.nodes[node_id].type_id == SUBNODE_OUTPUT_TYPE_ID
        )
        inserted_sink_id = next(
            node_id
            for node_id in inserted_node_id_set
            if workspace.nodes[node_id].type_id == "core.logger"
        )
        self.assertNotEqual(inserted_pin_id, original_pin_id)
        self.assertTrue(
            any(
                edge.source_node_id == inserted_shell_id
                and edge.source_port_key == inserted_pin_id
                and edge.target_node_id == inserted_sink_id
                and edge.target_port_key == "message"
                for edge in workspace.edges.values()
            )
        )

    def test_encoded_fragment_parent_keeps_external_parent_when_ids_collide(
        self,
    ) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        mutations = model.validated_mutations(workspace.workspace_id, registry)
        parent = mutations.add_node(type_id="core.logger", title="Parent", x=0.0, y=0.0)
        fragment_payload = build_graph_fragment_payload(
            nodes=[
                {
                    "ref_id": parent.node_id,
                    "type_id": "core.logger",
                    "title": "Child",
                    "x": 120.0,
                    "y": 80.0,
                    "collapsed": False,
                    "properties": {},
                    "exposed_ports": {},
                    "visual_style": {},
                    "parent_node_id": encode_fragment_external_parent_id(
                        parent.node_id
                    ),
                    "custom_width": None,
                    "custom_height": None,
                }
            ],
            edges=[],
        )

        inserted_node_ids = insert_graph_fragment(
            model=model,
            workspace_id=workspace.workspace_id,
            fragment_payload=fragment_payload,
            delta_x=0.0,
            delta_y=0.0,
        )

        self.assertEqual(len(inserted_node_ids), 1)
        inserted = workspace.nodes[inserted_node_ids[0]]
        self.assertEqual(inserted.parent_node_id, parent.node_id)
        self.assertNotEqual(inserted.parent_node_id, inserted.node_id)

    def test_registry_owns_catalog_rejects_unknown_ids_and_freezes_after_composition(
        self,
    ) -> None:
        first = NodeRegistry()
        second = NodeRegistry()
        self.assertIsNot(first.data_types, second.data_types)

        unknown_primary = NodeTypeSpec(
            "tests.unknown_primary",
            "Unknown Primary",
            ("Tests",),
            "",
            (PortSpec("value", "out", "data", "Packet.Unknown"),),
            (),
        )
        with self.assertRaisesRegex(
            ValueError, "unknown data-type ID 'Packet.Unknown'"
        ):
            first.register_descriptor(unknown_primary, _factory(unknown_primary))

        unknown_accepted = replace(
            unknown_primary,
            type_id="tests.unknown_accepted",
            ports=(
                PortSpec(
                    "value",
                    "out",
                    "data",
                    GRAPH_DATA_TYPE_ID,
                    accepted_data_types=("Packet.Unknown",),
                ),
            ),
        )
        with self.assertRaisesRegex(
            ValueError, "unknown data-type ID 'Packet.Unknown'"
        ):
            first.register_descriptor(unknown_accepted, _factory(unknown_accepted))

        dynamic = replace(
            unknown_primary,
            type_id="tests.unknown_dynamic",
            ports=(),
            properties=(
                PropertySpec(
                    "ids",
                    "json",
                    ["value"],
                    "Ids",
                    inspector_visible=False,
                ),
            ),
            dynamic_port_groups=(
                DynamicPortGroupSpec(
                    "outputs",
                    "ids",
                    "out",
                    lambda properties: (
                        PortSpec("value", "out", "data", "Packet.Unknown"),
                    ),
                    lambda properties: "value",
                ),
            ),
        )
        with self.assertRaisesRegex(
            ValueError, "unknown data-type ID 'Packet.Unknown'"
        ):
            first.register_descriptor(dynamic, _factory(dynamic))

        composed = build_default_registry()
        self.assertTrue(composed.data_types.is_frozen)








    def test_descriptor_and_plugin_bundle_registration_are_atomic(self) -> None:
        registry = NodeRegistry()
        valid = NodeTypeSpec(
            "tests.atomic.valid",
            "Atomic Valid",
            ("Tests",),
            "",
            (PortSpec("value", "out", "data", GRAPH_DATA_TYPE_ID),),
            (),
        )
        invalid = replace(
            valid,
            type_id="tests.atomic.invalid",
            ports=(PortSpec("value", "out", "data", "Packet.Unknown"),),
        )
        with self.assertRaisesRegex(ValueError, "Packet.Unknown"):
            registry.register_descriptors(
                (
                    PluginDescriptor(valid, _factory(valid)),
                    PluginDescriptor(invalid, _factory(invalid)),
                ),
            )
        self.assertIsNone(registry.spec_or_none(valid.type_id))

        family = DataTypeFamilySpec("packet", "Packet", "data.packet", "packet")
        packet_type = DataTypeSpec(
            "Packet.Data.Value",
            "Packet Value",
            "packet",
            lambda value: True,
            parents=(GRAPH_DATA_TYPE_ID,),
        )
        manifest = plugin_contracts.PluginContractManifest(
            data_type_families=(family,),
            data_types=(packet_type,),
        )
        plugin_spec = replace(
            valid,
            type_id="tests.atomic.plugin",
            ports=(PortSpec("value", "out", "data", packet_type.type_id),),
        )
        registry.register_plugin_bundle(
            manifest,
            (PluginDescriptor(plugin_spec, _factory(plugin_spec)),),
            owner_id="packet.atomic",
        )
        before_fingerprint = registry.data_types.fingerprint()

        with self.assertRaisesRegex(ValueError, "Packet.Unknown"):
            registry.register_plugin_bundle(
                manifest,
                (PluginDescriptor(invalid, _factory(invalid)),),
                owner_id="packet.atomic",
                replace_owner=True,
            )
        self.assertEqual(registry.data_types.fingerprint(), before_fingerprint)
        self.assertIsNotNone(registry.spec_or_none(plugin_spec.type_id))
        self.assertIsNone(registry.spec_or_none(invalid.type_id))

        dependent_spec = replace(
            valid,
            type_id="tests.atomic.dependent",
            ports=(
                PortSpec(
                    "value",
                    "in",
                    "data",
                    packet_type.type_id,
                    required=False,
                ),
            ),
        )
        registry.register_plugin_bundle(
            None,
            (PluginDescriptor(dependent_spec, _factory(dependent_spec)),),
            owner_id="packet.consumer",
        )
        before_fingerprint = registry.data_types.fingerprint()
        before_type_ids = {spec.type_id for spec in registry.all_specs()}
        replacement_family = DataTypeFamilySpec(
            "packet_next",
            "Packet Next",
            "data.packet",
            "packet",
        )
        replacement_type = DataTypeSpec(
            "Packet.Data.Next",
            "Packet Next",
            replacement_family.family_id,
            lambda value: True,
            parents=(GRAPH_DATA_TYPE_ID,),
        )

        with self.assertRaisesRegex(ValueError, "Packet.Data.Value"):
            registry.register_plugin_bundle(
                plugin_contracts.PluginContractManifest(
                    data_type_families=(replacement_family,),
                    data_types=(replacement_type,),
                ),
                (),
                owner_id="packet.atomic",
                replace_owner=True,
            )
        self.assertEqual(registry.data_types.fingerprint(), before_fingerprint)
        self.assertEqual(
            {spec.type_id for spec in registry.all_specs()},
            before_type_ids,
        )
        self.assertIsNotNone(registry.data_types.get(packet_type.type_id))
        self.assertIsNone(registry.data_types.get(replacement_type.type_id))

    def test_owner_replacement_rolls_back_when_surviving_type_uses_removed_family(
        self,
    ) -> None:
        registry = NodeRegistry()
        family = DataTypeFamilySpec(
            "packet.shared",
            "Packet Shared",
            "data.packet",
            "packet",
        )
        owner_type = DataTypeSpec(
            "Packet.Owner.Value",
            "Owner Value",
            family.family_id,
            lambda value: True,
            parents=(GRAPH_DATA_TYPE_ID,),
        )
        dependent_type = DataTypeSpec(
            "Packet.Consumer.Value",
            "Consumer Value",
            family.family_id,
            lambda value: True,
            parents=(GRAPH_DATA_TYPE_ID,),
        )
        owner_spec = NodeTypeSpec(
            "tests.catalog.owner",
            "Catalog Owner",
            ("Tests",),
            "",
            (PortSpec("value", "out", "data", owner_type.type_id),),
            (),
        )
        consumer_spec = replace(
            owner_spec,
            type_id="tests.catalog.consumer",
            display_name="Catalog Consumer",
            ports=(PortSpec("value", "out", "data", dependent_type.type_id),),
        )
        registry.register_plugin_bundle(
            plugin_contracts.PluginContractManifest(
                data_type_families=(family,),
                data_types=(owner_type,),
            ),
            (PluginDescriptor(owner_spec, _factory(owner_spec)),),
            owner_id="packet.owner",
        )
        registry.register_plugin_bundle(
            plugin_contracts.PluginContractManifest(
                data_types=(dependent_type,),
            ),
            (PluginDescriptor(consumer_spec, _factory(consumer_spec)),),
            owner_id="packet.consumer",
        )
        before_snapshot = registry.data_types.snapshot()
        before_fingerprint = registry.data_types.fingerprint()
        before_manifests = {
            owner_id: registry.plugin_contract_manifest(owner_id)
            for owner_id in ("packet.owner", "packet.consumer")
        }
        before_specs = {spec.type_id: spec for spec in registry.all_specs()}

        with self.assertRaisesRegex(ValueError, "unknown family 'packet.shared'"):
            registry.register_plugin_bundle(
                None,
                (),
                owner_id="packet.owner",
                replace_owner=True,
            )

        self.assertEqual(registry.data_types.snapshot(), before_snapshot)
        self.assertEqual(registry.data_types.fingerprint(), before_fingerprint)
        self.assertEqual(
            {
                owner_id: registry.plugin_contract_manifest(owner_id)
                for owner_id in before_manifests
            },
            before_manifests,
        )
        self.assertEqual(
            {spec.type_id: spec for spec in registry.all_specs()},
            before_specs,
        )

    def test_owner_replacement_rolls_back_when_surviving_conversion_loses_endpoint(
        self,
    ) -> None:
        registry = NodeRegistry()
        family = DataTypeFamilySpec(
            "packet.converted",
            "Packet Converted",
            "data.packet",
            "packet",
        )
        target_type = DataTypeSpec(
            "Packet.Converted.Value",
            "Converted Value",
            family.family_id,
            lambda value: True,
            parents=(GRAPH_DATA_TYPE_ID,),
        )
        owner_spec = NodeTypeSpec(
            "tests.conversion.owner",
            "Conversion Owner",
            ("Tests",),
            "",
            (PortSpec("value", "out", "data", target_type.type_id),),
            (),
        )
        consumer_spec = replace(
            owner_spec,
            type_id="tests.conversion.consumer",
            display_name="Conversion Consumer",
            ports=(PortSpec("value", "out", "data", GRAPH_DATA_TYPE_ID),),
        )
        registry.register_plugin_bundle(
            plugin_contracts.PluginContractManifest(
                data_type_families=(family,),
                data_types=(target_type,),
            ),
            (PluginDescriptor(owner_spec, _factory(owner_spec)),),
            owner_id="packet.owner",
        )
        registry.register_plugin_bundle(
            plugin_contracts.PluginContractManifest(
                data_conversions=(
                    DataConversionSpec(
                        GRAPH_DATA_TYPE_ID,
                        target_type.type_id,
                        lambda value: value,
                    ),
                ),
            ),
            (PluginDescriptor(consumer_spec, _factory(consumer_spec)),),
            owner_id="packet.consumer",
        )
        before_snapshot = registry.data_types.snapshot()
        before_fingerprint = registry.data_types.fingerprint()
        before_manifests = {
            owner_id: registry.plugin_contract_manifest(owner_id)
            for owner_id in ("packet.owner", "packet.consumer")
        }
        before_specs = {spec.type_id: spec for spec in registry.all_specs()}

        with self.assertRaisesRegex(
            ValueError,
            "references unknown endpoint 'Packet.Converted.Value'",
        ):
            registry.register_plugin_bundle(
                None,
                (),
                owner_id="packet.owner",
                replace_owner=True,
            )

        self.assertEqual(registry.data_types.snapshot(), before_snapshot)
        self.assertEqual(registry.data_types.fingerprint(), before_fingerprint)
        self.assertEqual(
            {
                owner_id: registry.plugin_contract_manifest(owner_id)
                for owner_id in before_manifests
            },
            before_manifests,
        )
        self.assertEqual(
            {spec.type_id: spec for spec in registry.all_specs()},
            before_specs,
        )

    def test_canonical_generic_compatibility_preserves_previous_any_semantics(
        self,
    ) -> None:
        data_types = build_default_registry().data_types
        self.assertTrue(
            data_types.compatibility(
                GRAPH_DATA_TYPE_ID,
                STRING_DATA_TYPE_ID,
            ).is_compatible
        )
        self.assertTrue(
            data_types.compatibility(
                STRING_DATA_TYPE_ID,
                GRAPH_DATA_TYPE_ID,
            ).is_compatible
        )
        self.assertFalse(
            data_types.compatibility(
                STRING_DATA_TYPE_ID,
                INTEGER_DATA_TYPE_ID,
            ).is_compatible
        )

    def test_default_registry_has_canonical_type_inventory_and_declared_special_cases(
        self,
    ) -> None:
        registry = build_default_registry(include_public_plugins=False)

        data_ports = [
            port
            for spec in registry.all_specs()
            for port in spec.ports
            if port.kind == "data"
        ]
        resolved_data_ports = [
            (spec.type_id, port)
            for spec in registry.all_specs()
            for port in resolve_instance_ports(
                spec,
                registry.default_properties(spec.type_id),
                data_types=registry.data_types,
            )
            if port.kind == "data"
        ]
        primary_type_ids = {port.data_type for port in data_ports}
        accepted_type_ids = {
            accepted_type
            for port in data_ports
            for accepted_type in port.accepted_data_types
        }

        self.assertEqual(len(registry.all_specs()), 144)
        self.assertEqual(len(data_ports), 437)
        self.assertEqual(len(resolved_data_ports), 442)
        self.assertEqual(len(primary_type_ids), 57)
        self.assertEqual(len(accepted_type_ids), 14)
        self.assertEqual(len({accepted for _, port in resolved_data_ports for accepted in port.accepted_data_types}), 16)
        self.assertEqual(len(registry.data_types.all_specs()), 167)
        self.assertEqual(
            len(
                [
                    spec
                    for spec in registry.data_types.all_specs()
                    if spec.type_id != LOAD_STEP_DATA_TYPE_ID
                ]
            ),
            166,
        )
        self.assertFalse(
            primary_type_ids
            & {
                "any",
                "bool",
                "int",
                "float",
                "str",
                "dict",
                "list",
                "interval_1d",
                "path",
                "json",
                "list[str]",
            }
        )
        static_port_keys = {
            (spec.type_id, port.key)
            for spec in registry.all_specs()
            for port in spec.ports
            if port.kind == "data"
        }
        self.assertEqual(
            {
                (type_id, port.key)
                for type_id, port in resolved_data_ports
                if (type_id, port.key) not in static_port_keys
            },
            {
                ("core.python_script", "payload"),
                ("core.python_script", "result"),
                ("model.viewer", "scene_1"),
                ("core.stream_gate", "output_0"),
                ("core.stream_gate", "output_1"),
            },
        )
        legacy_type_ids = {
            "any",
            "bool",
            "int",
            "float",
            "str",
            "dict",
            "list",
            "interval_1d",
            "path",
            "json",
            "list[str]",
        }
        for type_id, port in resolved_data_ports:
            for declared_type_id in (
                port.data_type,
                *port.accepted_data_types,
            ):
                self.assertNotIn(
                    declared_type_id,
                    legacy_type_ids,
                    (type_id, port.key, declared_type_id),
                )
                self.assertIsNotNone(
                    registry.data_types.get(declared_type_id),
                    (type_id, port.key, declared_type_id),
                )

        process_ports = {
            port.key: port for port in registry.get_spec("io.process_run").ports
        }
        self.assertEqual(process_ports["stdout"].data_type, GRAPH_DATA_TYPE_ID)
        self.assertEqual(process_ports["stderr"].data_type, GRAPH_DATA_TYPE_ID)

        self.assertEqual(
            registry.data_types.require(SSH_SFTP_SECRET_DATA_TYPE_ID).sensitivity,
            "secret",
        )
        self.assertEqual(
            registry.data_types.require(SSH_SFTP_HOST_DATA_TYPE_ID).persistence,
            "never",
        )

    def test_solution_reuse_scope_is_fail_closed_by_registry_entry_kind(self) -> None:
        registry = NodeRegistry()
        base = NodeTypeSpec(
            "tests.solution_scope",
            "Solution Scope",
            ("Tests",),
            "",
            (),
            (),
        )
        invalid = replace(base, solution_reuse_scope="global")  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "solution_reuse_scope"):
            registry.validate_spec(invalid)

        trusted = replace(base, solution_reuse_scope="session")
        with self.assertRaisesRegex(ValueError, "Trusted factory.*never"):
            registry.register_descriptor(trusted, _factory(trusted))

        passive = replace(
            base,
            runtime_behavior="passive",
            solution_reuse_scope="session",
        )
        with self.assertRaisesRegex(ValueError, "non-active.*never"):
            registry.validate_spec(passive)

        public = replace(
            base,
            type_id="custom.solution_scope.1234abcd",
            solution_reuse_scope="durable",
        )
        function_ref = PythonFunctionRef(
            bundle_id="public.bundle",
            bundle_digest="a" * 64,
            module_relative_path="node.py",
            function_name="run",
            source_digest="b" * 64,
        )
        with self.assertRaisesRegex(ValueError, "Untrusted function.*never"):
            registry.register_python_function(public, function_ref)

        non_custom_untrusted = replace(
            base,
            type_id="tests.non_custom_untrusted",
            solution_reuse_scope="durable",
        )
        with self.assertRaisesRegex(ValueError, "Untrusted function.*never"):
            registry.register_python_function(
                non_custom_untrusted,
                replace(function_ref, bundle_id="untrusted.bundle"),
            )

    def test_solution_reuse_scope_changes_registry_contract_fingerprint(self) -> None:
        function_ref = PythonFunctionRef(
            bundle_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
            bundle_digest="a" * 64,
            module_relative_path="node.py",
            function_name="run",
            source_digest="b" * 64,
        )
        base = NodeTypeSpec(
            "tests.solution_fingerprint",
            "Solution Fingerprint",
            ("Tests",),
            "",
            (),
            (),
        )
        first = NodeRegistry()
        first.register_python_function(base, function_ref)
        second = NodeRegistry()
        second._register_trusted_python_function(  # noqa: SLF001
            replace(base, solution_reuse_scope="session"),
            function_ref,
        )

        self.assertNotEqual(
            first.contract_fingerprint(),
            second.contract_fingerprint(),
        )

    def test_solution_provenance_overlay_is_registry_owned_and_trusted_only(self) -> None:
        registry = build_default_registry()
        for type_id in (
            "engineering.cad_import",
            "engineering.fe_import",
            "io.file_read",
            "io.image_import",
            "io.excel_read",
            "tabular.input",
        ):
            self.assertEqual(
                registry.get_spec(type_id).solution_provenance_inputs,
                (SolutionProvenanceInputSpec("path", "file"),),
            )

        base = NodeTypeSpec(
            "io.file_read",
            "Untrusted Lookalike",
            ("Tests",),
            "",
            (),
            (),
        )
        function_ref = PythonFunctionRef(
            bundle_id="untrusted.bundle",
            bundle_digest="a" * 64,
            module_relative_path="node.py",
            function_name="run",
            source_digest="b" * 64,
        )
        untrusted = NodeRegistry()
        untrusted.register_python_function(base, function_ref)
        self.assertEqual(
            untrusted.get_spec(base.type_id).solution_provenance_inputs,
            (),
        )
        with self.assertRaisesRegex(ValueError, "cannot supply solution provenance"):
            NodeRegistry().register_python_function(
                replace(
                    base,
                    solution_provenance_inputs=(
                        SolutionProvenanceInputSpec("path", "file"),
                    ),
                ),
                function_ref,
            )

    def test_execution_environment_facts_include_packages_addons_and_toolchains(
        self,
    ) -> None:
        facts = build_default_registry().execution_environment_facts()
        self.assertIn("numpy", facts["python_packages"])
        self.assertTrue(
            any(
                owner_id == "ea_node_editor.builtins.tabular_data"
                for owner_id, _enabled, _version in facts["addons"]
            )
        )
        self.assertTrue(
            any(
                toolchain_id == "tabular_data.python_runtime"
                for _owner, toolchain_id, _kind, _language, _requirements in facts[
                    "toolchains"
                ]
            )
        )


if __name__ == "__main__":
    unittest.main()
