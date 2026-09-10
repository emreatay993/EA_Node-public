from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ea_node_editor.addons.tabular_data import catalog as tabular_catalog
from ea_node_editor.addons.tabular_data.input_node import (
    TABULAR_DATA_INPUT_DISPLAY_NAME,
    TABULAR_DATA_INPUT_NODE_TYPE_ID,
)
from ea_node_editor.custom_workflows.codec import custom_workflow_library_items
from ea_node_editor.nodes.category_paths import category_display, category_key
from ea_node_editor.nodes.bootstrap import build_builtin_registry, build_default_registry
from ea_node_editor.runtime_contracts import (
    DOUBLE_DATA_TYPE_ID,
    GRAPH_DATA_TYPE_ID,
    INTEGER_DATA_TYPE_ID,
    STRING_DATA_TYPE_ID,
)
from ea_node_editor.ui.shell.library_projection import (
    build_combined_library_items,
    build_filtered_library_items,
    build_library_category_tree,
    build_library_category_options,
    build_library_data_type_options,
    build_registry_library_items,
    project_display_library_items,
    project_grouped_library_items,
    projected_port_declared_data_types,
    rank_node_library_usage,
)

from ea_node_editor.nodes.node_specs import DynamicPortGroupSpec, NodeTypeSpec, PortSpec, PropertySpec
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.runtime_contracts import (
    ARRAY_DATA_REF_TYPE_ID,
    PATH_DATA_TYPE_ID,
    TABULAR_DATA_REF_TYPE_ID,
)


class LibraryProjectionUsageRankingTests(unittest.TestCase):
    def test_recent_usage_ranks_by_frequency_then_recency_and_ignores_unavailable_items(
        self,
    ) -> None:
        items = [
            {
                "type_id": "core.alpha",
                "display_name": "Alpha",
                "library_source": "node_registry",
            },
            {
                "type_id": "core.beta",
                "display_name": "Beta",
                "library_source": "node_registry",
            },
            {
                "type_id": "core.gamma",
                "display_name": "Gamma",
                "library_source": "node_registry",
            },
            {
                "type_id": "core.delta",
                "display_name": "Delta",
                "library_source": "node_registry",
            },
            {
                "type_id": "core.epsilon",
                "display_name": "Epsilon",
                "library_source": "node_registry",
            },
            {
                "type_id": "core.zeta",
                "display_name": "Zeta",
                "library_source": "node_registry",
            },
            {
                "type_id": "custom_workflow:demo",
                "display_name": "Demo",
                "library_source": "custom_workflow",
            },
        ]

        ranked = rank_node_library_usage(
            combined_items=items,
            usage=[
                "core.delta",
                "core.epsilon",
                "core.zeta",
                "core.beta",
                "core.alpha",
                "custom_workflow:demo",
                "missing.node",
                "core.beta",
                "core.gamma",
                "core.alpha",
            ],
        )

        self.assertEqual(
            [item["type_id"] for item in ranked],
            ["core.alpha", "core.beta", "core.gamma", "core.zeta", "core.epsilon"],
        )


class LibraryProjectionRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        registry = build_default_registry()
        cls.data_types = registry.data_types
        registry_items = build_registry_library_items(
            registry_specs=registry.all_specs(), data_types=registry.data_types
        )
        cls.combined_items = build_combined_library_items(
            registry_items=registry_items,
            custom_workflow_items=[],
        )

    def test_projected_port_declared_types_keep_primary_then_unique_alternatives(
        self,
    ) -> None:
        self.assertEqual(
            projected_port_declared_data_types(
                {
                    "data_type": "Primary",
                    "accepted_data_types": ["Alternative", "Primary", "Alternative"],
                }
            ),
            ("Primary", "Alternative"),
        )
        for malformed in ({}, {"data_type": " "}, {"data_type": None}, {"data_type": 4}):
            self.assertEqual(projected_port_declared_data_types(malformed), ())

    def test_registry_library_items_keep_declared_data_port_order(self) -> None:
        excel_write_item = next(
            item
            for item in self.combined_items
            if str(item.get("type_id", "")) == "io.excel_write"
        )

        input_keys = [
            str(port.get("key", ""))
            for port in excel_write_item["ports"]
            if port.get("direction") == "in"
        ]
        output_keys = [
            str(port.get("key", ""))
            for port in excel_write_item["ports"]
            if port.get("direction") == "out"
        ]

        self.assertEqual(input_keys, ["rows", "path"])
        self.assertEqual(output_keys, ["written_path"])

    def test_library_rows_and_filter_options_use_default_resolved_dynamic_ports(self) -> None:
        registry = build_builtin_registry()
        dynamic = NodeTypeSpec(
            type_id="tests.dynamic_only", display_name="Dynamic", category_path=("Tests",),
            icon="", ports=(), properties=(PropertySpec("port_ids", "json", ["file"], "Ports"),),
            dynamic_port_groups=(DynamicPortGroupSpec(
                "outputs", "port_ids", "out",
                lambda properties: tuple(PortSpec(key, "out", "data", PATH_DATA_TYPE_ID) for key in properties["port_ids"]),
                lambda _properties: "next",
            ),),
        )
        items = build_registry_library_items(
            registry_specs=[registry.get_spec("core.python_script"), registry.get_spec("core.stream_gate"), dynamic],
            data_types=registry.data_types,
        )
        ports = {item["type_id"]: [port["key"] for port in item["ports"]] for item in items}
        self.assertEqual(ports["core.python_script"], ["payload", "result"])
        self.assertEqual(ports["core.stream_gate"], ["stream", "gate", "output_0", "output_1"])
        self.assertEqual(ports["tests.dynamic_only"], ["file"])
        self.assertIn(PATH_DATA_TYPE_ID, {item["value"] for item in build_library_data_type_options(combined_items=items)})

    def test_combined_projection_retains_node_but_omits_malformed_data_ports(self) -> None:
        ports = [
            {"key": f"bad_{index}", "direction": "in", "kind": "data", "data_type": value, "accepted_data_types": [GRAPH_DATA_TYPE_ID]}
            for index, value in enumerate((None, "", " ", 4, []))
        ]
        ports.append({"key": "valid", "direction": "in", "kind": "data", "data_type": DOUBLE_DATA_TYPE_ID})
        items = build_combined_library_items(
            registry_items=[],
            custom_workflow_items=[{"type_id": "custom_workflow:test", "display_name": "Test", "ports": ports}],
        )
        self.assertEqual([port["key"] for port in items[0]["ports"]], ["valid"])
        self.assertNotIn(GRAPH_DATA_TYPE_ID, {item["value"] for item in build_library_data_type_options(combined_items=items)})

    def test_registry_browser_payload_projects_help_metadata_and_real_port_labels(
        self,
    ) -> None:
        spec = NodeTypeSpec(
            type_id="example.sum",
            display_name="Sum",
            category_path=("Math",),
            icon="calculate",
            runtime_behavior="active",
            surface_family="standard",
            surface_variant="",
            description="Adds two values.",
            keywords=("add", "total"),
            ports=(
                PortSpec(
                    key="left_value",
                    label="Left Value",
                    description="First value to add.",
                    direction="in",
                    kind="data",
                    data_type=DOUBLE_DATA_TYPE_ID,
                    side="left",
                    exposed=True,
                ),
            ),
            properties=(),
        )

        item = build_registry_library_items(data_types=NodeRegistry().data_types, registry_specs=[spec])[0]

        self.assertEqual(item["keywords"], ["add", "total"])
        self.assertEqual(item["library_visual"]["kind"], "catalog_icon")
        self.assertEqual(item["ports"][0]["label"], "Left Value")
        self.assertEqual(item["ports"][0]["description"], "First value to add.")


class LibraryProjectionFolderExplorerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = build_default_registry()
        cls.registry_items = build_registry_library_items(
            registry_specs=cls.registry.all_specs(), data_types=cls.registry.data_types,
        )
        cls.combined_items = build_combined_library_items(
            registry_items=cls.registry_items,
            custom_workflow_items=[],
        )

    def test_folder_explorer_is_discoverable_in_input_output_library_group(
        self,
    ) -> None:
        folder_item = next(
            item
            for item in self.registry_items
            if str(item.get("type_id", "")) == "io.folder_explorer"
        )

        self.assertEqual(folder_item["display_name"], "Folder Explorer")
        self.assertEqual(folder_item["category_path"], ("Input / Output",))
        self.assertEqual(folder_item["category_key"], category_key(("Input / Output",)))
        self.assertEqual(folder_item["category_display"], "Input / Output")
        self.assertEqual(folder_item["library_source"], "node_registry")
        self.assertEqual(
            [port["key"] for port in folder_item["ports"]],
            ["current"],
        )

        filtered = build_filtered_library_items(
            combined_items=self.combined_items,
            query="folder explorer",
            category=category_key(("Input / Output",)),
            data_type="",
            direction="",
        )
        self.assertEqual([item["type_id"] for item in filtered], ["io.folder_explorer"])

        rows = project_grouped_library_items(
            category_tree=build_library_category_tree(filtered)
        )
        self.assertEqual([row["kind"] for row in rows], ["category", "node"])
        self.assertEqual(rows[0]["category_key"], category_key(("Input / Output",)))
        self.assertEqual(rows[1]["type_id"], "io.folder_explorer")
        self.assertEqual(
            rows[1]["ancestor_category_keys"], [category_key(("Input / Output",))]
        )


class LibraryProjectionTabularDataInputTests(unittest.TestCase):
    def test_tabular_data_input_library_item_is_availability_gated(self) -> None:
        with patch.object(tabular_catalog, "_find_spec", return_value=None):
            unavailable_registry = build_default_registry()
        self.assertIsNone(
            unavailable_registry.spec_or_none(TABULAR_DATA_INPUT_NODE_TYPE_ID)
        )

        with patch.object(tabular_catalog, "_find_spec", return_value=object()):
            registry = build_default_registry()
        registry_items = build_registry_library_items(
            registry_specs=registry.all_specs(), data_types=registry.data_types
        )
        tabular_item = next(
            item
            for item in registry_items
            if str(item.get("type_id", "")) == TABULAR_DATA_INPUT_NODE_TYPE_ID
        )

        self.assertEqual(tabular_item["display_name"], TABULAR_DATA_INPUT_DISPLAY_NAME)
        self.assertEqual(tabular_item["category_path"], ("Data",))
        self.assertEqual(tabular_item["library_source"], "node_registry")
        self.assertEqual(
            [port["key"] for port in tabular_item["ports"]],
            ["path", "table_data", "array_data"],
        )


def _port(
    *,
    key: str = "value",
    direction: str = "out",
    kind: str = "data",
    data_type: str = GRAPH_DATA_TYPE_ID,
    accepted_data_types: tuple[str, ...] = (),
) -> PortSpec:
    return PortSpec(
        key=key,
        direction=direction,
        kind=kind,
        data_type=data_type,
        accepted_data_types=accepted_data_types,
        side="",
        exposed=True,
    )


def _spec(
    type_id: str,
    display_name: str,
    category_path: tuple[str, ...],
    *,
    ports: tuple[PortSpec, ...] | None = None,
    icon: str = "fixture",
    runtime_behavior: str = "active",
    surface_family: str = "standard",
    surface_variant: str = "",
) -> NodeTypeSpec:
    return NodeTypeSpec(
        type_id=type_id,
        display_name=display_name,
        category_path=category_path,
        icon=icon,
        description=f"{display_name} description",
        ports=ports or (_port(),),
        properties=(),
        runtime_behavior=runtime_behavior,
        surface_family=surface_family,
        surface_variant=surface_variant,
    )


class LibraryProjectionNestedCategoryPayloadTests(unittest.TestCase):
    def test_registry_items_nested_category_library_payload_projects_path_metadata(
        self,
    ) -> None:
        path = ("Engineering Analysis", "Compute", "Stress")
        [item] = build_registry_library_items(
            data_types=NodeRegistry().data_types, registry_specs=[
                _spec("fixture.stress", "Stress", path),
            ]
        )

        self.assertEqual(item["category_path"], path)
        self.assertEqual(item["category_key"], category_key(path))
        self.assertEqual(item["category_display"], "Engineering Analysis > Compute > Stress")
        self.assertEqual(item["category"], "Engineering Analysis > Compute > Stress")
        self.assertEqual(item["root_category"], "Engineering Analysis")
        self.assertEqual(item["runtime_behavior"], "active")
        self.assertEqual(item["surface_family"], "standard")
        self.assertEqual(item["surface_variant"], "")
        self.assertEqual(
            item["library_visual"],
            {
                "kind": "catalog_icon",
                "runtime_behavior": "active",
                "surface_family": "standard",
                "surface_variant": "",
                "shape_id": "",
                "icon": "fixture",
            },
        )

    def test_grouped_rows_nested_category_library_payload_flattens_trie_with_metadata(
        self,
    ) -> None:
        registry_items = build_registry_library_items(
            data_types=NodeRegistry().data_types, registry_specs=[
                _spec("fixture.root_direct", "Root Direct", ("Root",)),
                _spec("fixture.beta_leaf", "Beta Leaf", ("Root", "Beta", "Leaf")),
                _spec("fixture.alpha_leaf", "Alpha Leaf", ("Root", "Alpha", "Leaf")),
                _spec("fixture.alpha_direct", "Alpha Direct", ("Root", "Alpha")),
            ]
        )
        rows = project_grouped_library_items(
            category_tree=build_library_category_tree(registry_items)
        )

        category_rows = [row for row in rows if row["kind"] == "category"]
        self.assertEqual(
            [row["category"] for row in category_rows],
            [
                "Root",
                "Root > Alpha",
                "Root > Alpha > Leaf",
                "Root > Beta",
                "Root > Beta > Leaf",
            ],
        )
        self.assertEqual(
            [row["label"] for row in category_rows],
            ["Root", "Alpha", "Leaf", "Beta", "Leaf"],
        )
        self.assertEqual([row["depth"] for row in category_rows], [0, 1, 2, 1, 2])
        self.assertEqual(
            category_rows[2]["ancestor_category_keys"],
            [category_key(("Root",)), category_key(("Root", "Alpha"))],
        )
        leaf_keys = {
            row["category_key"] for row in category_rows if row["label"] == "Leaf"
        }
        self.assertEqual(
            leaf_keys,
            {
                category_key(("Root", "Alpha", "Leaf")),
                category_key(("Root", "Beta", "Leaf")),
            },
        )
        root_category_index = next(
            index
            for index, row in enumerate(rows)
            if row["kind"] == "category" and row["category"] == "Root"
        )
        alpha_category_index = next(
            index
            for index, row in enumerate(rows)
            if row["kind"] == "category" and row["category"] == "Root > Alpha"
        )
        alpha_leaf_category_index = next(
            index
            for index, row in enumerate(rows)
            if row["kind"] == "category" and row["category"] == "Root > Alpha > Leaf"
        )
        alpha_direct_index = next(
            index
            for index, row in enumerate(rows)
            if row.get("type_id") == "fixture.alpha_direct"
        )
        root_direct_index = next(
            index
            for index, row in enumerate(rows)
            if row.get("type_id") == "fixture.root_direct"
        )
        alpha_direct_row = rows[alpha_direct_index]
        self.assertEqual(alpha_direct_row["library_visual"]["kind"], "catalog_icon")
        self.assertEqual(alpha_direct_row["runtime_behavior"], "active")
        self.assertLess(root_category_index, alpha_category_index)
        self.assertLess(alpha_category_index, alpha_leaf_category_index)
        self.assertLess(alpha_leaf_category_index, alpha_direct_index)
        self.assertLess(alpha_direct_index, root_direct_index)

    def test_display_rows_icon_mode_groups_passive_flowchart_visuals_into_tile_rows(
        self,
    ) -> None:
        registry_items = build_registry_library_items(
            data_types=NodeRegistry().data_types, registry_specs=[
                _spec("fixture.active", "Active Node", ("Flowchart",)),
                _spec(
                    "passive.flowchart.callout",
                    "Callout",
                    ("Flowchart",),
                    icon="chat_bubble",
                    runtime_behavior="passive",
                    surface_family="flowchart",
                    surface_variant="callout",
                ),
                _spec(
                    "passive.flowchart.process",
                    "Process",
                    ("Flowchart",),
                    icon="crop_din",
                    runtime_behavior="passive",
                    surface_family="flowchart",
                    surface_variant="process",
                ),
                _spec(
                    "passive.flowchart.decision",
                    "Decision",
                    ("Flowchart",),
                    icon="diamond",
                    runtime_behavior="passive",
                    surface_family="flowchart",
                    surface_variant="decision",
                ),
            ]
        )

        category_tree = build_library_category_tree(registry_items)
        text_rows = project_grouped_library_items(category_tree=category_tree)
        icon_rows = project_display_library_items(
            category_tree=category_tree,
            passive_node_library_display_mode="icon",
        )

        self.assertEqual(
            [row["kind"] for row in text_rows],
            ["category", "node", "node", "node", "node"],
        )
        self.assertEqual(
            [row["kind"] for row in icon_rows],
            ["category", "node", "passive_icon_grid"],
        )
        grid_row = icon_rows[2]
        self.assertEqual(
            grid_row["ancestor_category_keys"], [category_key(("Flowchart",))]
        )
        self.assertEqual(
            [item["type_id"] for item in grid_row["items"]],
            [
                "passive.flowchart.callout",
                "passive.flowchart.decision",
                "passive.flowchart.process",
            ],
        )
        callout_visual = grid_row["items"][0]["library_visual"]
        self.assertEqual(callout_visual["kind"], "flowchart_shape")
        self.assertEqual(callout_visual["shape_id"], "callout")
        self.assertEqual(callout_visual["icon"], "")
        self.assertGreater(callout_visual["aspect_ratio"], 1.0)

    def test_flowchart_multi_document_library_visual_uses_metric_contract_aspect_ratio(
        self,
    ) -> None:
        registry = build_default_registry()
        items = build_registry_library_items(registry_specs=registry.all_specs(), data_types=registry.data_types)
        item_by_type = {str(item["type_id"]): item for item in items}

        visual = item_by_type["passive.flowchart.multi_document"]["library_visual"]

        self.assertEqual(visual["kind"], "flowchart_shape")
        self.assertEqual(visual["shape_id"], "multi_document")
        self.assertAlmostEqual(visual["aspect_ratio"], 228.0 / 128.0, places=6)

    def test_filters_and_options_nested_category_library_payload_are_path_backed(
        self,
    ) -> None:
        combined_items = build_combined_library_items(
            registry_items=build_registry_library_items(
                data_types=NodeRegistry().data_types, registry_specs=[
                    _spec("fixture.compute", "Compute Node", ("Engineering Analysis", "Compute")),
                    _spec("fixture.viewer", "Viewer Node", ("Engineering Analysis", "Viewer")),
                    _spec("fixture.io", "Input Node", ("Input / Output",)),
                ]
            ),
            custom_workflow_items=[],
        )

        root_filtered = build_filtered_library_items(
            combined_items=combined_items,
            query="",
            category=category_key(("Engineering Analysis",)),
            data_type="",
            direction="",
        )
        self.assertEqual(
            {item["type_id"] for item in root_filtered},
            {"fixture.compute", "fixture.viewer"},
        )

        compute_filtered = build_filtered_library_items(
            combined_items=combined_items,
            query="",
            category=category_key(("Engineering Analysis", "Compute")),
            data_type="",
            direction="",
        )
        self.assertEqual(
            [item["type_id"] for item in compute_filtered], ["fixture.compute"]
        )

        query_filtered = build_filtered_library_items(
            combined_items=combined_items,
            query="Engineering Analysis > Viewer",
            category="",
            data_type="",
            direction="",
        )
        self.assertEqual(
            [item["type_id"] for item in query_filtered], ["fixture.viewer"]
        )

        options = build_library_category_options(
            combined_items=combined_items,
        )
        options_by_label = {option["label"]: option for option in options}
        self.assertEqual(
            options_by_label["Engineering Analysis"]["value"], category_key(("Engineering Analysis",))
        )
        self.assertEqual(
            options_by_label["Engineering Analysis > Compute"]["value"],
            category_key(("Engineering Analysis", "Compute")),
        )
        self.assertEqual(
            options_by_label["Input / Output"]["value"],
            category_key(("Input / Output",)),
        )

    def test_custom_workflows_nested_category_library_payload_use_single_segment_path(
        self,
    ) -> None:
        [custom_item] = custom_workflow_library_items(
            [
                {
                    "workflow_id": "wf_nested_payload",
                    "name": "Reusable Flow",
                    "ports": [],
                    "fragment": {
                        "kind": "ea-node-editor/graph-fragment",
                        "version": 2,
                        "nodes": [
                            {
                                "ref_id": "node_a",
                                "type_id": "core.constant",
                                "title": "Constant",
                                "x": 10.0,
                                "y": 20.0,
                                "collapsed": False,
                                "properties": {"value": 1},
                                "exposed_ports": {},
                                "parent_node_id": None,
                            }
                        ],
                        "edges": [],
                    },
                }
            ]
        )

        self.assertEqual(custom_item["category_path"], ("Custom Workflows",))
        self.assertEqual(
            custom_item["category_key"], category_key(("Custom Workflows",))
        )
        self.assertEqual(custom_item["category"], "Custom Workflows")

        [combined_item] = build_combined_library_items(
            registry_items=[],
            custom_workflow_items=[custom_item],
        )
        self.assertEqual(combined_item["category_path"], ("Custom Workflows",))
        self.assertEqual(combined_item["root_category"], "Custom Workflows")


def _projected_registry_items(registry):
    return build_combined_library_items(
        registry_items=build_registry_library_items(
            registry_specs=registry.all_specs(), data_types=registry.data_types,
        ),
        custom_workflow_items=[],
    )


def _library_filter(
    registry,
    query="",
    category="",
    data_type="",
    direction="",
    *,
    category_path=None,
):
    category_filter = (
        category_key(tuple(category_path)) if category_path is not None else category
    )
    return [
        SimpleNamespace(**item)
        for item in build_filtered_library_items(
            combined_items=_projected_registry_items(registry),
            query=query,
            category=category_filter,
            data_type=data_type,
            direction=direction,
        )
    ]


def _library_category_options_for_registry(registry):
    return build_library_category_options(
        combined_items=_projected_registry_items(registry),
    )


def _library_category_paths(registry):
    return [
        tuple(option["category_path"])
        for option in _library_category_options_for_registry(registry)
        if option.get("category_path")
    ]


def _library_leaf_categories(registry):
    return sorted(
        {str(item["category_display"]) for item in _projected_registry_items(registry)},
        key=str.casefold,
    )


_ANNOTATION_CATEGORY_PATH = ("Annotation",)
_UTILITIES_CATEGORY_PATH = ("Utilities",)
_CANVAS_CATEGORY_PATH = ("Utilities", "Canvas")
_FLOWCHART_CATEGORY_PATH = ("Flowchart",)
_INPUT_OUTPUT_CATEGORY_PATH = ("Input / Output",)
_PLANNING_CATEGORY_PATH = ("Planning",)


class LibraryProjectionRegistryCoverageTests(unittest.TestCase):
    def test_flowchart_category_exposes_locked_passive_catalog(self) -> None:
        registry = build_default_registry()
        results = _library_filter(registry, category_path=_FLOWCHART_CATEGORY_PATH)

        self.assertEqual(
            {spec.type_id for spec in results},
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
        self.assertTrue(results)
        self.assertTrue(all(spec.category == "Flowchart" for spec in results))

    def test_planning_category_exposes_locked_passive_catalog(self) -> None:
        registry = build_default_registry()
        results = _library_filter(registry, category_path=_PLANNING_CATEGORY_PATH)

        self.assertEqual(
            {spec.type_id for spec in results},
            {
                "passive.planning.task_card",
                "passive.planning.milestone_card",
                "passive.planning.risk_card",
                "passive.planning.decision_card",
            },
        )
        self.assertTrue(results)
        self.assertTrue(all(spec.category == "Planning" for spec in results))

    def test_annotation_category_exposes_locked_passive_catalog(self) -> None:
        registry = build_default_registry()
        results = _library_filter(registry, category_path=_ANNOTATION_CATEGORY_PATH)

        self.assertEqual(
            {spec.type_id for spec in results},
            {
                "passive.annotation.sticky_note",
                "passive.annotation.callout",
                "passive.annotation.section_header",
                "passive.annotation.text",
            },
        )
        self.assertTrue(results)
        self.assertTrue(all(spec.category == "Annotation" for spec in results))

    def test_group_is_listed_under_utilities_canvas_parent_and_leaf_filters(
        self,
    ) -> None:
        registry = build_default_registry()
        group_type_id = "passive.annotation.group_backdrop"

        parent_results = _library_filter(
            registry, query="group", category_path=_UTILITIES_CATEGORY_PATH
        )
        leaf_results = _library_filter(
            registry, query="group", category_path=_CANVAS_CATEGORY_PATH
        )

        self.assertIn(group_type_id, {spec.type_id for spec in parent_results})
        self.assertIn(group_type_id, {spec.type_id for spec in leaf_results})
        group_spec = next(
            spec for spec in leaf_results if spec.type_id == group_type_id
        )
        self.assertEqual(group_spec.display_name, "Group")
        self.assertEqual(group_spec.category_path, _CANVAS_CATEGORY_PATH)
        self.assertIn(_UTILITIES_CATEGORY_PATH, _library_category_paths(registry))
        self.assertIn(_CANVAS_CATEGORY_PATH, _library_category_paths(registry))

    def test_filter_by_text_and_category(self) -> None:
        registry = build_default_registry()
        results = _library_filter(
            registry, query="excel", category_path=_INPUT_OUTPUT_CATEGORY_PATH
        )
        type_ids = {spec.type_id for spec in results}
        self.assertIn("io.excel_read", type_ids)
        self.assertIn("io.excel_write", type_ids)

    def test_filter_by_data_type_and_direction(self) -> None:
        registry = build_default_registry()
        results = _library_filter(registry, data_type=PATH_DATA_TYPE_ID, direction="in")
        self.assertTrue(any(spec.type_id == "io.file_read" for spec in results))

    def test_tabular_data_input_is_filterable_when_addon_available(self) -> None:
        with patch.object(tabular_catalog, "_find_spec", return_value=object()):
            registry = build_default_registry()

        path_results = _library_filter(
            registry, data_type=PATH_DATA_TYPE_ID, direction="in"
        )
        tabular_results = _library_filter(
            registry,
            data_type=TABULAR_DATA_REF_TYPE_ID,
            direction="out",
        )
        array_results = _library_filter(
            registry,
            data_type=ARRAY_DATA_REF_TYPE_ID,
            direction="out",
        )

        self.assertIn(
            TABULAR_DATA_INPUT_NODE_TYPE_ID, {spec.type_id for spec in path_results}
        )
        self.assertEqual(
            [spec.type_id for spec in tabular_results],
            [TABULAR_DATA_INPUT_NODE_TYPE_ID],
        )
        self.assertEqual(
            [spec.type_id for spec in array_results], [TABULAR_DATA_INPUT_NODE_TYPE_ID]
        )

    def test_filter_by_direction_only_returns_matching_nodes(self) -> None:
        registry = build_default_registry()
        results = _library_filter(registry, direction="in")
        self.assertTrue(results)
        self.assertTrue(
            all(
                any(port["direction"] == "in" for port in spec.ports)
                for spec in results
            )
        )

    def test_combined_filters_apply_as_intersection(self) -> None:
        registry = build_default_registry()
        results = _library_filter(
            registry,
            query="write",
            category_path=_INPUT_OUTPUT_CATEGORY_PATH,
            direction="in",
            data_type=PATH_DATA_TYPE_ID,
        )
        self.assertEqual(
            [spec.type_id for spec in results],
            ["io.excel_write", "io.image_export", "io.file_write"],
        )

    def test_filter_results_use_stable_predictable_sorting(self) -> None:
        registry = build_default_registry()
        first = [
            spec.type_id
            for spec in _library_filter(
                registry, category_path=_INPUT_OUTPUT_CATEGORY_PATH
            )
        ]
        second = [
            spec.type_id
            for spec in _library_filter(
                registry, category_path=_INPUT_OUTPUT_CATEGORY_PATH
            )
        ]
        self.assertEqual(first, second)
        self.assertEqual(
            first,
            [
                spec.type_id
                for spec in sorted(
                    _library_filter(
                        registry, category_path=_INPUT_OUTPUT_CATEGORY_PATH
                    ),
                    key=lambda spec: (
                        spec.display_name.casefold(),
                        spec.type_id.casefold(),
                    ),
                )
            ],
        )

    def test_library_filters_primary_and_accepted_data_types_as_union(self) -> None:
        spec = NodeTypeSpec(
            type_id="tests.multi_input",
            display_name="Multi Input",
            category_path=("Tests",),
            icon="",
            ports=(
                PortSpec(
                    "receiver",
                    "in",
                    "data",
                    DOUBLE_DATA_TYPE_ID,
                    required=False,
                    accepted_data_types=(INTEGER_DATA_TYPE_ID, STRING_DATA_TYPE_ID),
                ),
                PortSpec("result", "out", "data", DOUBLE_DATA_TYPE_ID),
            ),
            properties=(),
        )
        combined = build_combined_library_items(
            registry_items=build_registry_library_items(
                data_types=build_default_registry().data_types,
                registry_specs=[spec],
            ),
            custom_workflow_items=[],
        )

        def matches(data_type: str, direction: str) -> list[dict[str, object]]:
            return build_filtered_library_items(
                combined_items=combined,
                query="",
                category="",
                data_type=data_type,
                direction=direction,
            )

        for data_type in (DOUBLE_DATA_TYPE_ID, INTEGER_DATA_TYPE_ID, STRING_DATA_TYPE_ID):
            with self.subTest(data_type=data_type):
                self.assertEqual(
                    [item["type_id"] for item in matches(data_type, "in")],
                    [spec.type_id],
                )
        self.assertEqual(
            [item["type_id"] for item in matches(DOUBLE_DATA_TYPE_ID, "out")],
            [spec.type_id],
        )

if __name__ == "__main__":
    unittest.main()
