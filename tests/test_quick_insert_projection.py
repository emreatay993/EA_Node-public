from __future__ import annotations

import copy
import unittest

from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.runtime_contracts import (
    BOOLEAN_DATA_TYPE_ID,
    DataConversionSpec,
    ENGINEERING_SCENE_DATA_TYPE_ID,
    GRAPH_ARRAY_DATA_TYPE_ID,
    GRAPH_DATA_TYPE_ID,
    GRAPH_DICTIONARY_DATA_TYPE_ID,
    INTEGER_DATA_TYPE_ID,
    JSON_DATA_TYPE_ID,
    JSON_VALUE_DATA_TYPE_ID,
    STRING_DATA_TYPE_ID,
)
from ea_node_editor.ui.shell.library_projection import (
    build_combined_library_items,
    build_registry_library_items,
)
from ea_node_editor.ui.shell.quick_insert_projection import (
    build_canvas_quick_insert_items,
    build_connection_quick_insert_items,
)


def _item(type_id: str, name: str, ports: list[dict[str, object]]) -> dict[str, object]:
    return {"type_id": type_id, "display_name": name, "ports": ports}


def _port(key: str, data_type: str, direction: str = "in", **extra) -> dict[str, object]:
    return {"key": key, "label": key, "direction": direction, "kind": "data", "data_type": data_type, **extra}


class QuickInsertProjectionTests(unittest.TestCase):
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

    def test_canvas_quick_insert_blank_query_returns_no_results(self) -> None:
        self.assertEqual(
            build_canvas_quick_insert_items(
                combined_items=self.combined_items,
                query="",
            ),
            [],
        )
        self.assertEqual(
            build_canvas_quick_insert_items(
                combined_items=self.combined_items,
                query="   ",
            ),
            [],
        )

    def test_canvas_quick_insert_non_empty_query_returns_matches(self) -> None:
        results = build_canvas_quick_insert_items(
            combined_items=self.combined_items,
            query="trigger",
        )

        self.assertTrue(results)
        type_ids = [str(item.get("type_id", "")) for item in results]
        self.assertIn("core.trigger", type_ids)

    def test_connection_quick_insert_blank_query_keeps_compatible_matches(self) -> None:
        results = build_connection_quick_insert_items(
            combined_items=self.combined_items,
            data_types=self.data_types,
            query="",
            source_direction="out",
            source_kind="data",
            source_data_type=STRING_DATA_TYPE_ID,
        )

        self.assertTrue(results)
        self.assertTrue(all(item.get("compatible_port_labels") for item in results))
        self.assertTrue(all(item["compatibility_kind"] not in {"generic", "runtime_check"} for item in results))
        self.assertEqual(build_connection_quick_insert_items(
            combined_items=self.combined_items, data_types=self.data_types, query=" ",
            source_direction="out", source_kind="data", source_data_type=GRAPH_DATA_TYPE_ID,
        ), [])

    def test_connection_quick_insert_filters_data_ports_by_type(self) -> None:
        results = build_connection_quick_insert_items(
            combined_items=self.combined_items,
            data_types=self.data_types,
            query="process",
            source_direction="out",
            source_kind="data",
            source_data_type=STRING_DATA_TYPE_ID,
            limit=100,
        )

        process_run = next(
            item for item in results if str(item.get("type_id", "")) == "io.process_run"
        )
        self.assertEqual(
            [str(port.get("key", "")) for port in process_run["compatible_ports"]],
            ["command", "stdin_text"],
        )
        incompatible = build_connection_quick_insert_items(
            combined_items=self.combined_items,
            data_types=self.data_types,
            query="process",
            source_direction="out",
            source_kind="data",
            source_data_type=BOOLEAN_DATA_TYPE_ID,
            limit=100,
        )
        self.assertNotIn(
            "io.process_run", {str(item.get("type_id", "")) for item in incompatible}
        )

    def test_connection_quick_insert_skips_missing_or_invalid_primary_types(self) -> None:
        for value in (None, "", " ", 4, []):
            with self.subTest(data_type=value):
                item = {"type_id": "tests.invalid", "display_name": "Invalid", "ports": [{
                    "key": "input", "direction": "in", "kind": "data", "data_type": value,
                    "accepted_data_types": [STRING_DATA_TYPE_ID],
                }]}
                self.assertEqual(build_connection_quick_insert_items(
                    combined_items=[item], data_types=self.data_types, query="",
                    source_direction="out", source_kind="data", source_data_type=STRING_DATA_TYPE_ID,
                ), [])
                self.assertEqual(build_connection_quick_insert_items(
                    combined_items=self.combined_items, data_types=self.data_types, query="",
                    source_direction="out", source_kind="data", source_data_type=value,
                ), [])

    def test_connection_quick_insert_treats_primary_and_accepted_types_as_union(
        self,
    ) -> None:
        items = [
            {
                "type_id": "tests.union",
                "display_name": "Union",
                "ports": [
                    {
                        "key": "input",
                        "label": "Input",
                        "direction": "in",
                        "kind": "data",
                        "data_type": STRING_DATA_TYPE_ID,
                        "accepted_data_types": [INTEGER_DATA_TYPE_ID],
                    },
                    {
                        "key": "output",
                        "label": "Output",
                        "direction": "out",
                        "kind": "data",
                        "data_type": INTEGER_DATA_TYPE_ID,
                        "accepted_data_types": [],
                    },
                ],
            }
        ]

        primary_matches = build_connection_quick_insert_items(
            combined_items=items,
            data_types=self.data_types,
            query="",
            source_direction="out",
            source_kind="data",
            source_data_type=STRING_DATA_TYPE_ID,
        )
        alternative_matches = build_connection_quick_insert_items(
            combined_items=items,
            data_types=self.data_types,
            query="",
            source_direction="out",
            source_kind="data",
            source_data_type=INTEGER_DATA_TYPE_ID,
        )
        reverse_matches = build_connection_quick_insert_items(
            combined_items=items,
            data_types=self.data_types,
            query="",
            source_direction="in",
            source_kind="data",
            source_data_type=STRING_DATA_TYPE_ID,
            source_accepted_data_types=(INTEGER_DATA_TYPE_ID,),
        )

        self.assertEqual(
            [port["key"] for port in primary_matches[0]["compatible_ports"]],
            ["input"],
        )
        self.assertEqual(
            [port["key"] for port in alternative_matches[0]["compatible_ports"]],
            ["input"],
        )
        self.assertEqual(
            [port["key"] for port in reverse_matches[0]["compatible_ports"]],
            ["output"],
        )

    def test_connection_quick_insert_excludes_hidden_ports_in_both_directions(
        self,
    ) -> None:
        for source_direction, candidate_direction in (("out", "in"), ("in", "out")):
            with self.subTest(source_direction=source_direction):
                results = build_connection_quick_insert_items(
                    combined_items=[
                        {
                            "type_id": "tests.hidden",
                            "display_name": "Hidden",
                            "ports": [
                                {
                                    "key": "hidden",
                                    "direction": candidate_direction,
                                    "kind": "data",
                                    "data_type": STRING_DATA_TYPE_ID,
                                    "exposed": False,
                                }
                            ],
                        }
                    ],
                    data_types=self.data_types,
                    query="",
                    source_direction=source_direction,
                    source_kind="data",
                    source_data_type=STRING_DATA_TYPE_ID,
                )

                self.assertEqual(results, [])

    def test_connection_quick_insert_retains_runtime_check_matches_in_both_directions(
        self,
    ) -> None:
        self.assertEqual(
            self.data_types.compatibility(
                GRAPH_DATA_TYPE_ID,
                STRING_DATA_TYPE_ID,
            ).status,
            "runtime_check",
        )
        item = {
            "type_id": "tests.runtime_check",
            "display_name": "Runtime Check",
            "ports": [
                {
                    "key": "concrete_input",
                    "direction": "in",
                    "kind": "data",
                    "data_type": STRING_DATA_TYPE_ID,
                },
                {
                    "key": "abstract_output",
                    "direction": "out",
                    "kind": "data",
                    "data_type": GRAPH_DATA_TYPE_ID,
                },
            ],
        }

        forward = build_connection_quick_insert_items(
            combined_items=[item],
            data_types=self.data_types,
            query="runtime check",
            source_direction="out",
            source_kind="data",
            source_data_type=GRAPH_DATA_TYPE_ID,
        )
        reverse = build_connection_quick_insert_items(
            combined_items=[item],
            data_types=self.data_types,
            query="runtime check",
            source_direction="in",
            source_kind="data",
            source_data_type=STRING_DATA_TYPE_ID,
        )

        self.assertEqual(
            [port["key"] for port in forward[0]["compatible_ports"]],
            ["concrete_input"],
        )
        self.assertEqual(
            [port["key"] for port in reverse[0]["compatible_ports"]],
            ["abstract_output"],
        )
        self.assertEqual(forward[0]["compatibility_label"], "Checked at runtime")
        self.assertEqual(reverse[0]["compatibility_label"], "Checked at runtime")

    def test_geometry_group_suggestions_are_precise_in_both_drag_directions(self) -> None:
        forward = build_connection_quick_insert_items(
            combined_items=self.combined_items, data_types=self.data_types, query="",
            source_direction="out", source_kind="data", source_data_type="COREX.Geometry.Group", limit=100,
        )
        by_id = {item["type_id"]: item for item in forward}
        self.assertIn("model.viewer", by_id)
        self.assertEqual(by_id["model.viewer"]["compatible_port_summaries"], ["Scene 1 — Exact type"])
        self.assertNotIn("io.file_write", by_id)
        self.assertNotIn("data.panel", by_id)
        reverse = build_connection_quick_insert_items(
            combined_items=self.combined_items, data_types=self.data_types, query="",
            source_direction="in", source_kind="data", source_data_type=ENGINEERING_SCENE_DATA_TYPE_ID,
            source_accepted_data_types=("COREX.Geometry.OCPBody", "COREX.Geometry.Group"), limit=100,
        )
        reverse_by_id = {item["type_id"]: item for item in reverse}
        self.assertEqual(reverse_by_id["geometry.construct_group"]["compatibility_kind"], "exact")
        self.assertNotIn("core.constant", reverse_by_id)
        searched = build_connection_quick_insert_items(
            combined_items=self.combined_items, data_types=self.data_types, query="python script",
            source_direction="in", source_kind="data", source_data_type=ENGINEERING_SCENE_DATA_TYPE_ID,
        )
        self.assertEqual(searched[0]["type_id"], "core.python_script")
        self.assertEqual(searched[0]["compatibility_kind"], "runtime_check")

    def test_best_tier_and_accepted_union_are_kept_without_mutating_library_rows(self) -> None:
        items = [_item("tests.best", "Best", [
            _port("broad", GRAPH_DATA_TYPE_ID),
            _port("second", STRING_DATA_TYPE_ID),
            _port("first", GRAPH_DATA_TYPE_ID, accepted_data_types=[STRING_DATA_TYPE_ID]),
            _port("parent", JSON_VALUE_DATA_TYPE_ID),
        ])]
        before = copy.deepcopy(items)
        result = build_connection_quick_insert_items(
            combined_items=items, data_types=self.data_types, query="",
            source_direction="out", source_kind="data", source_data_type=STRING_DATA_TYPE_ID,
        )[0]
        self.assertEqual([port["key"] for port in result["compatible_ports"]], ["second", "first"])
        self.assertEqual({port["matched_data_type"] for port in result["compatible_ports"]}, {STRING_DATA_TYPE_ID})
        self.assertEqual(result["compatibility_kind"], "exact")
        self.assertEqual(items, before)

    def test_tiers_sort_after_text_rank_and_filter_before_result_cap(self) -> None:
        catalog = NodeRegistry().data_types
        catalog.register_many(conversions=(DataConversionSpec(STRING_DATA_TYPE_ID, BOOLEAN_DATA_TYPE_ID, bool),), owner_id="tests.quick_insert")
        items = [
            _item("tests.parent", "Node A", [_port("value", JSON_VALUE_DATA_TYPE_ID)]),
            _item("tests.convert", "Node B", [_port("value", BOOLEAN_DATA_TYPE_ID)]),
            _item("tests.exact_many", "Node C", [_port("a", STRING_DATA_TYPE_ID), _port("b", STRING_DATA_TYPE_ID)]),
            _item("tests.exact", "Node Z", [_port("value", STRING_DATA_TYPE_ID)]),
            _item("tests.generic", "Node", [_port("value", GRAPH_DATA_TYPE_ID)]),
        ]
        blank = build_connection_quick_insert_items(combined_items=items, data_types=catalog, query="", source_direction="out", source_kind="data", source_data_type=STRING_DATA_TYPE_ID, limit=100)
        self.assertEqual([item["type_id"] for item in blank], ["tests.exact", "tests.exact_many", "tests.parent", "tests.convert"])
        self.assertEqual([item["compatibility_label"] for item in blank][-2:], ["Compatible type", "Converts automatically"])
        searched = build_connection_quick_insert_items(combined_items=items, data_types=catalog, query="node", source_direction="out", source_kind="data", source_data_type=STRING_DATA_TYPE_ID, limit=1)
        self.assertEqual(searched[0]["type_id"], "tests.generic")
        many_broad = [_item(f"tests.broad{index}", f"A {index}", [_port("value", GRAPH_DATA_TYPE_ID)]) for index in range(20)]
        capped = build_connection_quick_insert_items(combined_items=[*many_broad, items[3]], data_types=catalog, query="", source_direction="out", source_kind="data", source_data_type=STRING_DATA_TYPE_ID, limit=1)
        self.assertEqual(capped[0]["type_id"], "tests.exact")

    def test_structural_exact_matches_are_search_only_and_runtime_status_takes_priority(self) -> None:
        for data_type in (GRAPH_DATA_TYPE_ID, JSON_DATA_TYPE_ID, GRAPH_ARRAY_DATA_TYPE_ID, GRAPH_DICTIONARY_DATA_TYPE_ID):
            exact_items = [_item("tests.broad", "Broad", [_port("value", data_type)])]
            self.assertEqual(build_connection_quick_insert_items(combined_items=exact_items, data_types=self.data_types, query="", source_direction="out", source_kind="data", source_data_type=data_type), [])
            exact = build_connection_quick_insert_items(combined_items=exact_items, data_types=self.data_types, query="broad", source_direction="out", source_kind="data", source_data_type=data_type)[0]
            self.assertEqual(exact["compatibility_kind"], "generic")
        items = [_item("tests.metadata", "Metadata", [_port("metadata", GRAPH_DICTIONARY_DATA_TYPE_ID)])]
        blank = build_connection_quick_insert_items(combined_items=items, data_types=self.data_types, query="", source_direction="out", source_kind="data", source_data_type=GRAPH_DICTIONARY_DATA_TYPE_ID)
        self.assertEqual(blank, [])
        for source_type, expected in ((GRAPH_DICTIONARY_DATA_TYPE_ID, "Broad data match"), (GRAPH_DATA_TYPE_ID, "Checked at runtime")):
            result = build_connection_quick_insert_items(combined_items=items, data_types=self.data_types, query="metadata", source_direction="out", source_kind="data", source_data_type=source_type)[0]
            self.assertEqual(result["compatibility_label"], expected)
        unknown = [_item("tests.unknown", "Unknown", [_port("unknown", "Unknown.Type")])]
        self.assertEqual(build_connection_quick_insert_items(combined_items=unknown, data_types=self.data_types, query="unknown", source_direction="out", source_kind="data", source_data_type=GRAPH_DATA_TYPE_ID), [])

    def test_connection_quick_insert_neutral_flow_source_returns_flowchart_nodes(
        self,
    ) -> None:
        results = build_connection_quick_insert_items(
            combined_items=self.combined_items,
            data_types=self.data_types,
            query="",
            source_direction="neutral",
            source_kind="flow",
            source_data_type="flow",
            limit=100,
        )

        self.assertTrue(results)
        results_by_type = {str(item.get("type_id", "")): item for item in results}
        self.assertIn("passive.flowchart.process", results_by_type)
        self.assertIn("passive.planning.task_card", results_by_type)
        self.assertIn("passive.annotation.sticky_note", results_by_type)
        self.assertIn("passive.media.mail_panel", results_by_type)
        self.assertNotIn("core.start", results_by_type)
        self.assertEqual(
            results_by_type["passive.flowchart.process"]["compatible_port_labels"],
            ["top", "right", "bottom", "left"],
        )
        self.assertEqual(
            results_by_type["passive.planning.task_card"]["compatible_port_labels"],
            ["top", "right", "bottom", "left"],
        )
        self.assertEqual(
            results_by_type["passive.flowchart.process"]["compatible_direction"],
            "neutral",
        )


class QuickInsertProjectionCategoryTests(unittest.TestCase):
    def test_quick_insert_nested_category_library_payload_shows_full_path(
        self,
    ) -> None:
        path = ("Engineering Analysis", "Compute")
        combined_items = build_combined_library_items(
            registry_items=[
                {
                    "type_id": "fixture.quick_insert",
                    "display_name": "Quick Insert Candidate",
                    "category_path": path,
                    "description": "Quick Insert Candidate description",
                    "ports": [
                        {
                            "key": "target",
                            "direction": "in",
                            "kind": "data",
                            "data_type": GRAPH_DATA_TYPE_ID,
                        }
                    ],
                }
            ],
            custom_workflow_items=[],
        )

        canvas_results = build_canvas_quick_insert_items(
            combined_items=combined_items,
            query="Engineering Analysis > Compute",
        )
        self.assertEqual(canvas_results[0]["category"], "Engineering Analysis > Compute")
        self.assertEqual(canvas_results[0]["category_display"], "Engineering Analysis > Compute")

        connection_results = build_connection_quick_insert_items(
            combined_items=combined_items,
            data_types=build_default_registry().data_types,
            query="Engineering Analysis > Compute",
            source_direction="out",
            source_kind="data",
            source_data_type=GRAPH_DATA_TYPE_ID,
        )
        self.assertEqual(connection_results[0]["category"], "Engineering Analysis > Compute")


if __name__ == "__main__":
    unittest.main()
