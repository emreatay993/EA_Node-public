from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ea_node_editor.addons.tabular_data import catalog as tabular_catalog
from ea_node_editor.addons.tabular_data.input_node import (
    TABULAR_DATA_INPUT_NODE_TYPE_ID,
)
from ea_node_editor.graph.records import NodeLinkRecord
from ea_node_editor.nodes.category_paths import category_display
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.node_specs import PropertyConditionSpec, PropertySpec
from ea_node_editor.runtime_contracts import Interval1D
from ea_node_editor.ui.shell.inspector_projection import (
    build_selected_node_header_data,
    build_selected_node_link_items,
    build_selected_node_property_items,
)
from ea_node_editor.ui.shell.inspector_flow import coerce_editor_input_value


class InspectorProjectionFolderExplorerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = build_default_registry()

    def test_folder_explorer_current_path_property_is_folder_path_editor_payload(
        self,
    ) -> None:
        spec = self.registry.get_spec("io.folder_explorer")
        node = SimpleNamespace(
            type_id="io.folder_explorer",
            node_id="node-folder-explorer",
            properties={"current_path": "C:/Projects/Input"},
            port_labels={},
            exposed_ports={},
        )

        items = build_selected_node_property_items(
            node=node,
            spec=spec,
            subnode_pin_type_ids=set(),
        )
        items_by_key = {str(item["key"]): item for item in items}

        self.assertEqual(set(items_by_key), {"current_path"})
        current_path = items_by_key["current_path"]
        self.assertEqual(current_path["label"], "Current Path")
        self.assertEqual(current_path["type"], "path")
        self.assertEqual(current_path["editor_mode"], "path")
        self.assertEqual(current_path["inline_editor"], "")
        self.assertEqual(current_path["path_dialog_mode"], "folder")
        self.assertEqual(current_path["group"], "Source")


class InspectorProjectionNodeLinkTests(unittest.TestCase):
    def test_selected_node_link_items_preserve_order_and_resolve_target_metadata(
        self,
    ) -> None:
        node = SimpleNamespace(
            links=[
                NodeLinkRecord(
                    link_id="link-url",
                    kind="url",
                    title="Project docs",
                    target="https://example.com/docs",
                    subtitle="",
                ),
                NodeLinkRecord(
                    link_id="link-file",
                    kind="file",
                    title="Report",
                    target=r"C:\Projects\reports\summary.pdf",
                    subtitle="Local copy",
                ),
                NodeLinkRecord(
                    link_id="link-node",
                    kind="node",
                    title="Logger node",
                    target="node-logger",
                ),
                NodeLinkRecord(
                    link_id="link-cross-node",
                    kind="node",
                    title="PDF2",
                    target="node-pdf2",
                    target_workspace_id="ws-reports",
                    target_node_id="node-pdf2",
                ),
                NodeLinkRecord(
                    link_id="link-workspace",
                    kind="workspace",
                    title="Analysis workspace",
                    target="ws-analysis",
                ),
                NodeLinkRecord(
                    link_id="link-missing",
                    kind="node",
                    title="Missing target",
                    target="node-missing",
                ),
            ],
        )
        workspace_nodes = {
            "node-logger": SimpleNamespace(title="Logger", type_id="core.logger"),
        }
        workspaces = {
            "ws-analysis": SimpleNamespace(name="Analysis"),
            "ws-reports": SimpleNamespace(
                name="Reports",
                nodes={
                    "node-pdf2": SimpleNamespace(title="PDF2", type_id="media.panel"),
                },
            ),
        }

        items = build_selected_node_link_items(
            node=node,
            workspace_nodes=workspace_nodes,
            workspaces=workspaces,
        )

        self.assertEqual(
            [item["id"] for item in items],
            [
                "link-url",
                "link-file",
                "link-node",
                "link-cross-node",
                "link-workspace",
                "link-missing",
            ],
        )
        self.assertEqual(items[0]["kind"], "url")
        self.assertEqual(items[0]["type_label"], "Web")
        self.assertEqual(items[0]["breadcrumb"], "example.com")
        self.assertEqual(items[0]["icon"], "world-www")
        self.assertEqual(items[0]["type_color"], "#3BA9F5")
        self.assertFalse(items[0]["can_move_up"])
        self.assertTrue(items[0]["can_move_down"])

        self.assertEqual(items[1]["breadcrumb"], "Local copy")
        self.assertEqual(items[1]["icon"], "file-text")
        self.assertEqual(items[2]["breadcrumb"], "Logger")
        self.assertEqual(items[2]["icon"], "hierarchy-2")
        self.assertEqual(items[3]["breadcrumb"], "Reports - PDF2")
        self.assertEqual(items[3]["target_workspace_id"], "ws-reports")
        self.assertEqual(items[3]["target_node_id"], "node-pdf2")
        self.assertEqual(items[4]["breadcrumb"], "Analysis")
        self.assertEqual(items[4]["icon"], "layout-dashboard")
        self.assertEqual(items[5]["breadcrumb"], "Missing node")
        self.assertTrue(items[5]["can_move_up"])
        self.assertFalse(items[5]["can_move_down"])
        self.assertEqual([item["index"] for item in items], [0, 1, 2, 3, 4, 5])


class InspectorProjectionTabularDataInputTests(unittest.TestCase):
    def test_tabular_data_input_property_items_use_file_path_and_semantic_groups(
        self,
    ) -> None:
        with patch.object(tabular_catalog, "_find_spec", return_value=object()):
            registry = build_default_registry()
        spec = registry.get_spec(TABULAR_DATA_INPUT_NODE_TYPE_ID)
        node = SimpleNamespace(
            type_id=TABULAR_DATA_INPUT_NODE_TYPE_ID,
            node_id="node-tabular-input",
            properties={"path": "C:/Projects/data/weather.csv"},
            port_labels={},
            exposed_ports={},
        )

        items = build_selected_node_property_items(
            node=node,
            spec=spec,
            subnode_pin_type_ids=set(),
        )
        items_by_key = {str(item["key"]): item for item in items}

        self.assertEqual(items_by_key["path"]["editor_mode"], "path")
        self.assertEqual(items_by_key["path"]["path_dialog_mode"], "file")
        self.assertEqual(items_by_key["path"]["group"], "Source")
        self.assertEqual(items_by_key["selected_object"]["label"], "Data Source")
        self.assertEqual(items_by_key["selected_object"]["group"], "Selection")
        self.assertIn("multiple sheets", items_by_key["selected_object"]["help_text"])
        self.assertNotIn("array_slice_2d", items_by_key)
        self.assertEqual(items_by_key["array_slice_2d_row_start"]["label"], "Start Row")
        self.assertEqual(items_by_key["array_slice_2d_row_start"]["value"], 1)
        self.assertEqual(items_by_key["array_slice_2d_row_count"]["value"], 50)
        self.assertEqual(items_by_key["array_slice_2d_column_start"]["value"], "A")
        self.assertEqual(items_by_key["array_slice_2d_column_count"]["value"], 50)
        self.assertEqual(
            items_by_key["array_slice_2d_summary"]["editor_mode"], "summary"
        )
        self.assertEqual(
            items_by_key["array_slice_2d_summary"]["value"], "Rows 1-50, Columns A-AX"
        )
        self.assertEqual(items_by_key["cache_policy"]["group"], "Cache")
        self.assertEqual(items_by_key["project_managed_source"]["group"], "Portability")

    def test_tabular_selection_items_come_from_property_edit_adapter(self) -> None:
        with patch.object(tabular_catalog, "_find_spec", return_value=object()):
            registry = build_default_registry()
        spec = registry.get_spec(TABULAR_DATA_INPUT_NODE_TYPE_ID)
        node = SimpleNamespace(
            type_id=TABULAR_DATA_INPUT_NODE_TYPE_ID,
            node_id="node-tabular-input",
            properties={"path": "C:/Projects/data/weather.csv"},
            port_labels={},
            exposed_ports={},
        )

        items = build_selected_node_property_items(
            node=node,
            spec=spec,
            subnode_pin_type_ids=set(),
            property_edit_adapters=(),
        )
        items_by_key = {str(item["key"]): item for item in items}

        self.assertNotIn("array_slice_2d", items_by_key)
        self.assertNotIn("array_slice_2d_row_start", items_by_key)
        self.assertNotIn("array_slice_2d_summary", items_by_key)
        self.assertNotIn("help_text", items_by_key["selected_object"])


class InspectorProjectionHeaderTests(unittest.TestCase):
    def test_header_nested_category_library_payload_shows_full_path(
        self,
    ) -> None:
        path = ("Engineering Analysis", "Compute")
        header = build_selected_node_header_data(
            node=SimpleNamespace(
                title="", type_id="fixture.quick_insert", node_id="node-1"
            ),
            spec=SimpleNamespace(
                display_name="Quick Insert Candidate",
                description="Quick Insert Candidate description",
                category="Engineering Analysis",
                category_path=path,
            ),
            workflow_nodes={"node-1": SimpleNamespace(type_id="fixture.quick_insert")},
        )
        metadata = {item["label"]: item["value"] for item in header["metadata_items"]}
        self.assertEqual(metadata["Category"], "Engineering Analysis > Compute")


class InspectorProjectionPropertyGroupTests(unittest.TestCase):
    def test_interval_editor_input_keeps_declared_endpoint_order(self) -> None:
        default = Interval1D(0.0, 1.0)

        self.assertEqual(
            coerce_editor_input_value(
                "interval_1d", {"start": 8.0, "end": 2.0}, default
            ),
            Interval1D(8.0, 2.0),
        )
        self.assertIs(
            coerce_editor_input_value(
                "interval_1d", {"start": True, "end": 2.0}, default
            ),
            default,
        )
        self.assertIs(
            coerce_editor_input_value(
                "interval_1d", {"start": float("nan"), "end": 2.0}, default
            ),
            default,
        )
        self.assertIs(
            coerce_editor_input_value(
                "interval_1d", {"start": 2.0, "end": float("inf")}, default
            ),
            default,
        )

    def test_property_items_reuse_interval_and_condition_presentation(self) -> None:
        spec = SimpleNamespace(
            type_id="fixture.inspector_interval",
            display_name="Inspector Interval",
            category_path=("Fixtures",),
            category=category_display(("Fixtures",)),
            icon="fixture",
            ports=(),
            dynamic_port_groups=(),
            instance_spec_resolver=None,
            properties=(
                PropertySpec(
                    key="mode",
                    type="enum",
                    default="None",
                    label="Mode",
                    enum_values=("None", "Manual"),
                    inline_editor="enum",
                ),
                PropertySpec(
                    key="color_map",
                    type="enum",
                    default="Rainbow",
                    label="Color map",
                    enum_values=("Rainbow", "Viridis"),
                    inline_editor="enum",
                    searchable=True,
                ),
                PropertySpec(
                    key="result_bound",
                    type="interval_1d",
                    default=Interval1D(10.0, 2.0),
                    label="Result bound",
                    minimum=0.0,
                    maximum=10.0,
                    step=0.5,
                    inline_editor="interval_slider",
                    interval_direction="decreasing",
                    enabled_when=PropertyConditionSpec("mode", ("Manual",)),
                ),
            ),
        )
        node = SimpleNamespace(
            type_id=spec.type_id,
            node_id="node-interval",
            properties={},
        )

        items = {
            str(item["key"]): item
            for item in build_selected_node_property_items(
                node=node,
                spec=spec,
                subnode_pin_type_ids=set(),
            )
        }
        interval = items["result_bound"]

        self.assertEqual(interval["editor_mode"], "interval_slider")
        self.assertEqual(interval["value"], {"start": 10.0, "end": 2.0})
        self.assertEqual(interval["display_value"], {"start": 10.0, "end": 2.0})
        self.assertFalse(interval["condition_enabled"])
        self.assertFalse(interval["editor_enabled"])
        self.assertEqual(
            interval["editor_disabled_reason"],
            "Available when Mode is Manual.",
        )
        self.assertTrue(items["color_map"]["searchable"])

        node.properties["mode"] = "Manual"
        enabled_interval = {
            str(item["key"]): item
            for item in build_selected_node_property_items(
                node=node,
                spec=spec,
                subnode_pin_type_ids=set(),
            )
        }["result_bound"]
        self.assertTrue(enabled_interval["condition_enabled"])
        self.assertTrue(enabled_interval["editor_enabled"])

    def test_property_items_emit_group_with_fallback_when_unset(self) -> None:
        spec = SimpleNamespace(
            type_id="fixture.grouped",
            display_name="Grouped Node",
            category_path=("Fixtures",),
            category=category_display(("Fixtures",)),
            icon="fixture",
            description="Grouped Node description",
            ports=(),
            dynamic_port_groups=(),
            instance_spec_resolver=None,
            properties=(
                PropertySpec(
                    key="source_path",
                    type="str",
                    default="",
                    label="Source Path",
                    group="Source",
                ),
                PropertySpec(
                    key="comment",
                    type="str",
                    default="",
                    label="Comment",
                ),
            ),
        )
        node = SimpleNamespace(
            type_id="fixture.grouped",
            node_id="node-1",
            properties={},
        )

        items = build_selected_node_property_items(
            node=node,
            spec=spec,
            subnode_pin_type_ids=set(),
        )
        items_by_key = {str(item["key"]): item for item in items}

        self.assertEqual(items_by_key["source_path"]["group"], "Source")
        self.assertEqual(items_by_key["comment"]["group"], "Properties")

    def test_property_items_flag_dirty_when_value_differs_from_default(self) -> None:
        spec = SimpleNamespace(
            type_id="fixture.dirty",
            display_name="Dirty Node",
            category_path=("Fixtures",),
            category=category_display(("Fixtures",)),
            icon="fixture",
            description="Dirty Node description",
            ports=(),
            dynamic_port_groups=(),
            instance_spec_resolver=None,
            properties=(
                PropertySpec(
                    key="source_path",
                    type="str",
                    default="",
                    label="Source Path",
                ),
                PropertySpec(
                    key="nodes_only",
                    type="bool",
                    default=False,
                    label="Nodes Only",
                ),
            ),
        )

        def _items_for(properties: dict) -> dict:
            node = SimpleNamespace(
                type_id="fixture.dirty",
                node_id="node-1",
                properties=properties,
            )
            items = build_selected_node_property_items(
                node=node,
                spec=spec,
                subnode_pin_type_ids=set(),
            )
            return {str(item["key"]): item for item in items}

        absent = _items_for({})
        self.assertFalse(absent["source_path"]["dirty"])
        self.assertFalse(absent["nodes_only"]["dirty"])

        equal_to_default = _items_for({"source_path": "", "nodes_only": False})
        self.assertFalse(equal_to_default["source_path"]["dirty"])
        self.assertFalse(equal_to_default["nodes_only"]["dirty"])

        diverged = _items_for({"source_path": "C:/data/run.rst", "nodes_only": True})
        self.assertTrue(diverged["source_path"]["dirty"])
        self.assertTrue(diverged["nodes_only"]["dirty"])

        mixed = _items_for({"source_path": "C:/data/run.rst"})
        self.assertTrue(mixed["source_path"]["dirty"])
        self.assertFalse(mixed["nodes_only"]["dirty"])

    def test_web_page_viewer_start_location_uses_source_storage_picker(self) -> None:
        registry = build_default_registry()
        spec = registry.get_spec("web.page_viewer")
        node = SimpleNamespace(
            type_id="web.page_viewer",
            node_id="node-web",
            port_labels={},
            exposed_ports={},
            properties={
                "start_location": "https://example.com",
                "persist_browser_state": True,
            },
        )

        items = build_selected_node_property_items(
            node=node,
            spec=spec,
            subnode_pin_type_ids=set(),
        )
        items_by_key = {str(item["key"]): item for item in items}
        start_location = items_by_key["start_location"]

        self.assertEqual(start_location["editor_mode"], "path")
        self.assertEqual(start_location["path_dialog_mode"], "file")
        self.assertEqual(
            start_location["path_source_modes"], ["managed_copy", "external_link"]
        )
        self.assertTrue(start_location["path_supports_managed_copy"])
        self.assertTrue(start_location["path_supports_external_link"])
        self.assertEqual(start_location["path_current_source_mode"], "external_link")
        self.assertEqual(start_location["group"], "Source")

        node.properties["start_location"] = "temp://managed_html"
        items = build_selected_node_property_items(
            node=node,
            spec=spec,
            subnode_pin_type_ids=set(),
        )
        start_location = {str(item["key"]): item for item in items}["start_location"]
        self.assertEqual(start_location["path_current_source_mode"], "managed_copy")


if __name__ == "__main__":
    unittest.main()
