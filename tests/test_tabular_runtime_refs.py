from __future__ import annotations

import unittest

from ea_node_editor.execution.run_messages import (
    NodeSettledEvent,
)
from ea_node_editor.execution.viewer_messages import (
    OpenViewerSessionCommand,
    ViewerDataMaterializedEvent,
)
from ea_node_editor.execution.protocol_codec import (
    command_to_dict,
    dict_to_command,
    dict_to_event,
    event_to_dict,
)
from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
from ea_node_editor.runtime_contracts import (
    ArrayDataRef,
    ArrayDataResolver,
    ArrayMaterializationOptions,
    ArraySlice2D,
    ArraySlice2DRef,
    ArraySlice2DRequest,
    DataTree,
    TabularArrowBatchOptions,
    TabularColumn,
    TabularDataRef,
    TabularDataResolver,
    TabularDataWindow,
    TabularMaterializationOptions,
    TabularSchema,
    TabularWindowRef,
    TabularWindowRequest,
    deserialize_runtime_value,
    serialize_runtime_value,
)


class _FakeTabularResolver:
    def schema(self, ref: TabularDataRef) -> TabularSchema:
        return TabularSchema(
            columns=(TabularColumn("station", "str"), TabularColumn("temperature", "float64")),
            row_count=ref.row_count,
        )

    def metadata(self, ref: TabularDataRef) -> dict[str, object]:
        return {"ref_id": ref.ref_id, "source_uri": ref.source_uri}

    def window(self, ref: TabularDataRef, request: TabularWindowRequest) -> TabularDataWindow:
        return TabularDataWindow(
            columns=("station", "temperature")[: request.column_limit],
            rows=({"station": "A", "temperature": 21.5},),
            row_offset=request.row_offset,
            column_offset=request.column_offset,
            total_rows=ref.row_count,
            total_columns=ref.column_count,
        )

    def rows(self, _ref: TabularDataRef, request: TabularWindowRequest):
        return self.window(
            TabularDataRef(ref_id="table_runtime", resolver_id="tabular.cache", row_count=1, column_count=2),
            request,
        ).rows

    def arrow_batches(self, _ref: TabularDataRef, _options: TabularArrowBatchOptions):
        return iter(({"batch": 1},))

    def to_pandas(self, _ref: TabularDataRef, options: TabularMaterializationOptions):
        return {"backend": "pandas", "row_limit": options.row_limit}

    def to_polars(self, _ref: TabularDataRef, options: TabularMaterializationOptions):
        return {"backend": "polars", "row_limit": options.row_limit}

    def to_numpy(self, _ref: TabularDataRef, options: TabularMaterializationOptions):
        return {"backend": "numpy", "row_limit": options.row_limit}


class _FakeArrayResolver:
    def metadata(self, ref: ArrayDataRef) -> dict[str, object]:
        return {"ref_id": ref.ref_id, "shape": list(ref.shape)}

    def slice_2d(self, ref: ArrayDataRef, request: ArraySlice2DRequest) -> ArraySlice2D:
        return ArraySlice2D(
            values=((1.0, 2.0),),
            row_offset=request.row_offset,
            column_offset=request.column_offset,
            shape=ref.shape,
            dtype=ref.dtype,
        )

    def to_numpy(self, _ref: ArrayDataRef, options: ArrayMaterializationOptions):
        return {"backend": "numpy", "max_elements": options.max_elements}


class TabularRuntimeRefTests(unittest.TestCase):
    def test_tabular_and_array_refs_round_trip_through_runtime_value_codec(self) -> None:
        table_ref = TabularDataRef(
            ref_id="table_runtime_001",
            resolver_id="tabular.cache",
            backend_id="duckdb",
            source_uri="file:///data/weather.parquet",
            object_id="weather",
            row_count=1000,
            column_count=4,
            metadata={"warnings": ["large_data"], "preview": {"rows": 50}},
        )
        array_ref = ArrayDataRef(
            ref_id="array_runtime_001",
            resolver_id="tabular.cache",
            backend_id="npy_mmap",
            source_uri="file:///data/image.npy",
            object_id="image",
            shape=(4096, 4096),
            dtype="float32",
            metadata={"mmap": True},
        )
        window_ref = TabularWindowRef(
            ref_id="window_runtime_001",
            table_data=table_ref,
            row_offset=10,
            row_limit=0,
            column_offset=0,
            column_limit=0,
            columns=("station", "temperature"),
            metadata={"purpose": "export"},
        )
        slice_ref = ArraySlice2DRef(
            ref_id="slice_runtime_001",
            array_data=array_ref,
            row_offset=2,
            row_limit=3,
            column_offset=1,
            column_limit=0,
            metadata={"purpose": "debug"},
        )

        payload = serialize_runtime_value(
            {"table": table_ref, "array": array_ref, "window": window_ref, "slice": slice_ref}
        )

        self.assertEqual(
            payload["table"],
            {
                "__ea_runtime_value__": "tabular_data_ref",
                "data_type_id": "COREX.Runtime.TabularDataRef",
                "schema_version": 1,
                "ref_id": "table_runtime_001",
                "resolver_id": "tabular.cache",
                "backend_id": "duckdb",
                "source_uri": "file:///data/weather.parquet",
                "object_id": "weather",
                "row_count": 1000,
                "column_count": 4,
                "metadata": {"warnings": ["large_data"], "preview": {"rows": 50}},
            },
        )
        self.assertEqual(
            payload["array"],
            {
                "__ea_runtime_value__": "array_data_ref",
                "data_type_id": "COREX.Runtime.ArrayDataRef",
                "schema_version": 1,
                "ref_id": "array_runtime_001",
                "resolver_id": "tabular.cache",
                "backend_id": "npy_mmap",
                "source_uri": "file:///data/image.npy",
                "object_id": "image",
                "shape": [4096, 4096],
                "dtype": "float32",
                "metadata": {"mmap": True},
            },
        )
        self.assertEqual(payload["window"]["__ea_runtime_value__"], "tabular_window_ref")
        self.assertEqual(payload["window"]["table_data"]["__ea_runtime_value__"], "tabular_data_ref")
        self.assertEqual(payload["window"]["row_limit"], 0)
        self.assertEqual(payload["window"]["columns"], ["station", "temperature"])
        self.assertEqual(payload["slice"]["__ea_runtime_value__"], "array_slice_2d_ref")
        self.assertEqual(payload["slice"]["array_data"]["__ea_runtime_value__"], "array_data_ref")
        self.assertEqual(payload["slice"]["column_limit"], 0)

        restored = deserialize_runtime_value(payload)
        self.assertIsInstance(restored["table"], TabularDataRef)
        self.assertIsInstance(restored["array"], ArrayDataRef)
        self.assertIsInstance(restored["window"], TabularWindowRef)
        self.assertIsInstance(restored["slice"], ArraySlice2DRef)
        self.assertEqual(restored["table"].row_count, 1000)
        self.assertEqual(restored["array"].shape, (4096, 4096))
        self.assertEqual(restored["window"].table_data.ref_id, "table_runtime_001")
        self.assertEqual(restored["slice"].array_data.ref_id, "array_runtime_001")

    def test_refs_reject_non_json_safe_metadata(self) -> None:
        with self.assertRaisesRegex(TypeError, "metadata must contain only strict JSON"):
            TabularDataRef(
                ref_id="table_runtime_bad",
                resolver_id="tabular.cache",
                metadata={"bad": object()},
            )

        with self.assertRaisesRegex(ValueError, "metadata must contain only finite"):
            ArrayDataRef(
                ref_id="array_runtime_bad",
                resolver_id="tabular.cache",
                metadata={"bad": float("nan")},
            )
        with self.assertRaisesRegex(TypeError, "metadata must contain only strict JSON"):
            TabularWindowRef(
                ref_id="window_runtime_bad",
                table_data=TabularDataRef(ref_id="table_runtime", resolver_id="tabular.cache"),
                metadata={"bad": object()},
            )
        with self.assertRaisesRegex(ValueError, "metadata must contain only finite"):
            ArraySlice2DRef(
                ref_id="slice_runtime_bad",
                array_data=ArrayDataRef(ref_id="array_runtime", resolver_id="tabular.cache"),
                metadata={"bad": float("inf")},
            )

    def test_execution_protocol_round_trips_tabular_refs_in_node_and_viewer_payloads(self) -> None:
        table_ref = TabularDataRef(ref_id="table_runtime", resolver_id="tabular.cache", row_count=10, column_count=2)
        array_ref = ArrayDataRef(ref_id="array_runtime", resolver_id="tabular.cache", shape=(10, 2), dtype="float64")
        window_ref = TabularWindowRef(ref_id="window_runtime", table_data=table_ref, row_limit=0, column_limit=0)
        slice_ref = ArraySlice2DRef(ref_id="slice_runtime", array_data=array_ref, row_limit=0, column_limit=0)

        node_payload = event_to_dict(
            NodeSettledEvent(
                run_id="run_tabular",
                workspace_id="ws_main",
                node_id="node_tabular",
                outputs={
                    key: SettledPortResult(
                        status="value",
                        value=DataTree.from_item(value),
                    )
                    for key, value in {
                        "table": table_ref,
                        "array": array_ref,
                        "window": window_ref,
                        "slice": slice_ref,
                    }.items()
                },
            )
        )
        for key, marker in {
            "table": "tabular_data_ref",
            "array": "array_data_ref",
            "window": "tabular_window_ref",
            "slice": "array_slice_2d_ref",
        }.items():
            item = node_payload["outputs"][key]["value"]["branches"][0]["items"][0]
            self.assertEqual(item["__ea_runtime_value__"], marker)
        restored_node = dict_to_event(node_payload)
        self.assertEqual(restored_node.outputs["table"].value, DataTree.from_item(table_ref))
        self.assertEqual(restored_node.outputs["array"].value, DataTree.from_item(array_ref))
        self.assertEqual(restored_node.outputs["window"].value, DataTree.from_item(window_ref))
        self.assertEqual(restored_node.outputs["slice"].value, DataTree.from_item(slice_ref))

        command_payload = command_to_dict(
            OpenViewerSessionCommand(
                request_id="viewer_req_tabular",
                workspace_id="ws_main",
                node_id="node_tabular",
                session_id="session_tabular",
                backend_id="tabular.preview",
                data_refs={"table": table_ref, "array": array_ref, "window": window_ref, "slice": slice_ref},
                transport={"kind": "tabular_refs", "refs": [table_ref, array_ref, window_ref, slice_ref]},
            )
        )
        self.assertEqual(command_payload["data_refs"]["table"]["__ea_runtime_value__"], "tabular_data_ref")
        self.assertEqual(command_payload["transport"]["refs"][1]["__ea_runtime_value__"], "array_data_ref")
        self.assertEqual(command_payload["transport"]["refs"][2]["__ea_runtime_value__"], "tabular_window_ref")
        self.assertEqual(command_payload["transport"]["refs"][3]["__ea_runtime_value__"], "array_slice_2d_ref")
        restored_command = dict_to_command(command_payload)
        self.assertIsInstance(restored_command.data_refs["table"], TabularDataRef)
        self.assertIsInstance(restored_command.data_refs["array"], ArrayDataRef)
        self.assertIsInstance(restored_command.data_refs["window"], TabularWindowRef)
        self.assertIsInstance(restored_command.data_refs["slice"], ArraySlice2DRef)

        materialized_payload = event_to_dict(
            ViewerDataMaterializedEvent(
                request_id="viewer_req_tabular",
                workspace_id="ws_main",
                node_id="node_tabular",
                session_id="session_tabular",
                backend_id="tabular.preview",
                data_refs={"table": table_ref},
            )
        )
        restored_materialized = dict_to_event(materialized_payload)
        self.assertIsInstance(restored_materialized.data_refs["table"], TabularDataRef)

    def test_resolver_contracts_are_bounded_and_require_explicit_materialization_options(self) -> None:
        table_ref = TabularDataRef(ref_id="table_runtime", resolver_id="tabular.cache", row_count=1, column_count=2)
        array_ref = ArrayDataRef(ref_id="array_runtime", resolver_id="tabular.cache", shape=(1, 2), dtype="float64")
        table_resolver = _FakeTabularResolver()
        array_resolver = _FakeArrayResolver()

        self.assertIsInstance(table_resolver, TabularDataResolver)
        self.assertIsInstance(array_resolver, ArrayDataResolver)
        self.assertEqual(
            table_resolver.window(table_ref, TabularWindowRequest(row_limit=50, column_limit=2)).to_payload(),
            {
                "columns": ["station", "temperature"],
                "rows": [{"station": "A", "temperature": 21.5}],
                "row_offset": 0,
                "column_offset": 0,
                "total_rows": 1,
                "total_columns": 2,
            },
        )
        self.assertEqual(
            array_resolver.slice_2d(array_ref, ArraySlice2DRequest(row_limit=1, column_limit=2)).to_payload(),
            {
                "values": [[1.0, 2.0]],
                "row_offset": 0,
                "column_offset": 0,
                "shape": [1, 2],
                "dtype": "float64",
            },
        )

        with self.assertRaisesRegex(ValueError, "Tabular materialization requires"):
            TabularMaterializationOptions()
        with self.assertRaisesRegex(ValueError, "Array materialization requires"):
            ArrayMaterializationOptions()
        with self.assertRaisesRegex(ValueError, "row_limit must be > 0"):
            TabularMaterializationOptions(row_limit=0)
        with self.assertRaisesRegex(ValueError, "max_elements must be > 0"):
            ArrayMaterializationOptions(max_elements=0)
        self.assertEqual(TabularWindowRequest(row_limit=0, column_limit=1).row_limit, 0)
        self.assertEqual(ArraySlice2DRequest(row_limit=1, column_limit=0).column_limit, 0)

        self.assertEqual(
            table_resolver.to_pandas(table_ref, TabularMaterializationOptions(row_limit=50))["row_limit"],
            50,
        )
        self.assertEqual(
            array_resolver.to_numpy(array_ref, ArrayMaterializationOptions(max_elements=2))["max_elements"],
            2,
        )


if __name__ == "__main__":
    unittest.main()
