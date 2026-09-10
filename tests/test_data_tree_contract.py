from __future__ import annotations

import unittest

from ea_node_editor.nodes.decorators import in_port, out_port
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.nodes.node_specs import (
    NodeTypeSpec,
    PortSpec,
)
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.runtime_contracts import (
    COREX_VIEWER_SESSION_HANDLE_KIND,
    ArrayDataRef,
    DataTree,
    RuntimeArtifactRef,
    RuntimeHandleRef,
    TabularDataRef,
    deserialize_runtime_value,
    serialize_runtime_value,
)


class DataTreeContractTests(unittest.TestCase):
    def test_tree_orders_paths_and_keeps_python_containers_as_items(self) -> None:
        list_item = [1, 2]
        dict_item = {"value": 3}
        tree = DataTree(
            (
                ((2, 1), ("later",)),
                ((0,), (None, list_item, dict_item)),
                ((2, 0), ("earlier",)),
            )
        )

        self.assertEqual(tree.paths, ((0,), (2, 0), (2, 1)))
        self.assertEqual(tree[(0,)], (None, list_item, dict_item))
        self.assertEqual(tree.branch_count, 3)
        self.assertEqual(tree.item_count, 5)
        self.assertIs(DataTree.from_item(list_item)[(0,)][0], list_item)
        with self.assertRaisesRegex(ValueError, "duplicate path"):
            DataTree((((0,), (1,)), ((0,), (2,))))

    def test_merge_concatenates_equal_paths_in_tree_order(self) -> None:
        first = DataTree({(0,): ("a",), (2,): ("first",)})
        second = DataTree({(0,): ("b", "c"), (1,): ("middle",)})

        merged = first.merge(second)

        self.assertEqual(merged.paths, ((0,), (1,), (2,)))
        self.assertEqual(merged[(0,)], ("a", "b", "c"))
        self.assertEqual(merged[(1,)], ("middle",))
        self.assertEqual(merged[(2,)], ("first",))

    def test_modifiers_follow_the_locked_corex_rules(self) -> None:
        source = DataTree({(2, 1): ("a", "b"), (2, 0): ("c",), (3,): ()})

        self.assertEqual(
            source.graft(),
            DataTree({(2, 0, 0): ("c",), (2, 1, 0): ("a",), (2, 1, 1): ("b",)}),
        )
        self.assertEqual(source.flatten(), DataTree({(0,): ("c", "a", "b")}))
        self.assertEqual(
            DataTree({(4, 8, 0): ("a",), (4, 8, 2): ("b",)}).simplify(),
            DataTree({(0,): ("a",), (2,): ("b",)}),
        )
        self.assertEqual(
            DataTree({(4, 8, 0): ("a",)}).simplify(),
            DataTree({(0,): ("a",)}),
        )
        self.assertEqual(
            DataTree({(0,): (1, 2), (1,): (3, 4)}).reverse(),
            DataTree({(0,): (2, 1), (1,): (4, 3)}),
        )
        self.assertEqual(
            DataTree({(0,): (None, "a", None), (1,): (None,), (2,): ()}).clean(),
            DataTree({(0,): ("a",)}),
        )

    def test_modifier_selection_always_uses_pipeline_order(self) -> None:
        source = DataTree({(1,): (None, "a")})

        result = source.apply_modifiers(("clean", "graft"))

        self.assertEqual(result, DataTree({(1, 1): ("a",)}))
        with self.assertRaisesRegex(ValueError, "Unsupported DataTree modifier"):
            source.apply_modifiers(("unknown",))  # type: ignore[arg-type]

    def test_runtime_marker_recursively_round_trips_existing_refs_and_none(
        self,
    ) -> None:
        artifact = RuntimeArtifactRef.staged(
            "tree_artifact",
            data_type_id="COREX.DataTypes.Path",
            schema_version=1,
            format="bin",
            size_bytes=0,
            sha256="0" * 64,
            provenance="corex.test.fixture",
        )
        handle = RuntimeHandleRef(
            data_type_id="COREX.Viewer.Session",
            schema_version=1,
            handle_id="tree_handle",
            kind=COREX_VIEWER_SESSION_HANDLE_KIND,
            owner_scope="run:tree",
            worker_generation=2,
        )
        table = TabularDataRef(ref_id="tree_table", resolver_id="tabular.cache")
        array = ArrayDataRef(ref_id="tree_array", resolver_id="tabular.cache")
        tree = DataTree(
            {
                (0,): (
                    None,
                    artifact,
                    {"refs": [handle, table, array]},
                )
            }
        )
        catalog = NodeRegistry().data_types

        payload = serialize_runtime_value(tree, catalog=catalog)
        restored = deserialize_runtime_value(payload, catalog=catalog)

        self.assertEqual(payload["__ea_runtime_value__"], "data_tree")
        self.assertEqual(payload["branches"][0]["path"], [0])
        self.assertIsInstance(restored, DataTree)
        self.assertIsNone(restored[(0,)][0])
        self.assertIsInstance(restored[(0,)][1], RuntimeArtifactRef)
        nested = restored[(0,)][2]["refs"]
        self.assertIsInstance(nested[0], RuntimeHandleRef)
        self.assertIsInstance(nested[1], TabularDataRef)
        self.assertIsInstance(nested[2], ArrayDataRef)
        self.assertEqual(
            serialize_runtime_value(restored, catalog=catalog),
            payload,
        )


class DataTreeNodeSdkContractTests(unittest.TestCase):
    def test_port_access_defaults_and_decorators_are_public(self) -> None:
        item_port = PortSpec("value", "in", "data", "COREX.DataTypes.GraphDictionary")
        list_port = in_port(
            "values", data_type="COREX.DataTypes.Double", data_access="list"
        )
        tree_port = out_port(
            "tree",
            data_type="COREX.DataTypes.Any",
            data_access="tree",
        )

        self.assertEqual(item_port.data_access, "item")
        self.assertEqual(list_port.data_access, "list")
        self.assertEqual(tree_port.data_access, "tree")

    def test_registry_rejects_old_control_kinds_and_invalid_access(self) -> None:
        registry = NodeRegistry()
        old_control = NodeTypeSpec(
            type_id="tests.old_control",
            display_name="Old Control",
            category_path=("Tests",),
            icon="code",
            ports=(PortSpec("exec_in", "in", "exec", "exec"),),  # type: ignore[arg-type]
            properties=(),
        )
        invalid_access = NodeTypeSpec(
            type_id="tests.invalid_access",
            display_name="Invalid Access",
            category_path=("Tests",),
            icon="code",
            ports=(
                PortSpec(
                    "value",
                    "in",
                    "data",
                    "COREX.DataTypes.Any",
                    data_access="matrix",  # type: ignore[arg-type]
                ),
            ),
            properties=(),
        )

        with self.assertRaisesRegex(ValueError, "invalid kind: exec"):
            registry.register_descriptor(old_control, lambda: object())  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "invalid data_access: matrix"):
            registry.register_descriptor(invalid_access, lambda: object())  # type: ignore[arg-type]

    def test_execution_context_exposes_iteration_target_and_result_has_no_completed_flag(
        self,
    ) -> None:
        context = ExecutionContext(
            run_id="run",
            node_id="node",
            workspace_id="workspace",
            inputs={},
            properties={},
            emit_log=lambda _level, _message: None,
            target_path=(2, 3),
            target_iteration=4,
            iteration_count=6,
            trigger={"source": "manual"},
        )

        self.assertEqual(context.target_path, (2, 3))
        self.assertEqual(context.target_iteration, 4)
        self.assertEqual(context.iteration_count, 6)
        self.assertEqual(context.trigger, {"source": "manual"})
        with self.assertRaises(TypeError):
            NodeResult(completed=True)  # type: ignore[call-arg]


if __name__ == "__main__":
    unittest.main()
