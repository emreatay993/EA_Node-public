from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from ea_node_editor.addons.property_edit_adapters import PropertyEditAdapterContext
from ea_node_editor.addons.tabular_data.function_nodes import SOURCE as TABULAR_FUNCTION_SOURCE
from ea_node_editor.addons.tabular_data.extraction_nodes import (
    TABULAR_ARRAY_SLICE_2D_NODE_TYPE_ID,
    TABULAR_TABLE_WINDOW_NODE_TYPE_ID,
    TABULAR_WRITE_ARRAY_SLICE_2D_NODE_TYPE_ID,
    TABULAR_WRITE_TABLE_WINDOW_NODE_TYPE_ID,
    execute_array_slice_2d,
    execute_materialize_table_filter,
    execute_table_filter,
    execute_write_array_slice_2d,
    execute_write_table_filter,
    load_array_slice_2d,
    load_table_window,
    write_array_rows_to_path,
    write_table_rows_to_path,
)
from ea_node_editor.addons.tabular_data.input_node import execute_tabular_input
from ea_node_editor.addons.tabular_data.property_edit_adapter import create_tabular_property_edit_adapters
from ea_node_editor.execution.runtime_snapshot import RuntimeSnapshot, RuntimeSnapshotContext
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.file_dialog_filters import (
    TABULAR_ARRAY_OUTPUT_FILES_FILTER,
    TABULAR_TABLE_OUTPUT_FILES_FILTER,
)
from ea_node_editor.nodes.function_plugin import INTERNAL_BUILTIN_FUNCTION_OWNER_ID
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.persistence.artifact_resolution import ProjectArtifactResolver
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.runtime_contracts import (
    ARRAY_SLICE_2D_REF_TYPE_ID,
    GRAPH_ARRAY_DATA_TYPE_ID,
    GRAPH_DICTIONARY_DATA_TYPE_ID,
    PATH_DATA_TYPE_ID,
    TABULAR_WINDOW_REF_TYPE_ID,
    ArrayDataRef,
    ArraySlice2DRef,
    RuntimeArtifactRef,
    TabularDataRef,
    TabularWindowRef,
)


def _context(
    *,
    inputs: dict | None = None,
    properties: dict | None = None,
    logs: list[tuple[str, str]] | None = None,
    project_path: str = "",
    runtime_snapshot: RuntimeSnapshot | None = None,
    runtime_snapshot_context: RuntimeSnapshotContext | None = None,
    path_resolver=None,  # noqa: ANN001
    node_type_id: str = "",
) -> ExecutionContext:
    return ExecutionContext(
        run_id="run_tabular_extraction",
        node_id="node_tabular_extraction",
        workspace_id="ws_tabular_extraction",
        inputs=dict(inputs or {}),
        properties=dict(properties or {}),
        emit_log=lambda level, message: logs.append((level, message)) if logs is not None else None,
        trigger={},
        project_path=project_path,
        runtime_snapshot=runtime_snapshot,
        runtime_snapshot_context=runtime_snapshot_context,
        path_resolver=path_resolver or (lambda _value: None),
        node_type_id=node_type_id,
    )


def _table_ref(tmp_path: Path) -> TabularDataRef:
    source = tmp_path / "weather.csv"
    source.write_text("station,temp,pressure\nA,21.5,100\nB,22.0,101\n", encoding="utf-8")
    result = execute_tabular_input(_context(properties={"path": str(source)}))
    ref = result.outputs["table_data"]
    assert isinstance(ref, TabularDataRef)
    return ref


def _array_ref(tmp_path: Path) -> ArrayDataRef:
    numpy = pytest.importorskip("numpy")
    source = tmp_path / "array.npy"
    numpy.save(source, numpy.arange(12).reshape(3, 4))
    result = execute_tabular_input(_context(properties={"path": str(source)}))
    ref = result.outputs["array_data"]
    assert isinstance(ref, ArrayDataRef)
    return ref


def test_extraction_node_descriptors_publish_guided_ref_interfaces() -> None:
    specs_by_type_id = {
        declaration.spec.type_id: declaration.spec
        for declaration in discover_plugin_declarations(
            TABULAR_FUNCTION_SOURCE,
            allow_reserved_ids=True,
            owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
        )
    }
    table_spec = specs_by_type_id[TABULAR_TABLE_WINDOW_NODE_TYPE_ID]
    array_spec = specs_by_type_id[TABULAR_ARRAY_SLICE_2D_NODE_TYPE_ID]
    table_writer_spec = specs_by_type_id[TABULAR_WRITE_TABLE_WINDOW_NODE_TYPE_ID]
    array_writer_spec = specs_by_type_id[TABULAR_WRITE_ARRAY_SLICE_2D_NODE_TYPE_ID]
    table_materializer_spec = specs_by_type_id["tabular.materialize_table_filter"]
    array_materializer_spec = specs_by_type_id["tabular.materialize_array_slice_2d"]

    specs = (
        table_spec,
        array_spec,
        table_writer_spec,
        array_writer_spec,
        table_materializer_spec,
        array_materializer_spec,
    )
    assert all(port.kind == "data" for spec in specs for port in spec.ports)
    assert all(spec.settings_groups == () for spec in specs)

    assert table_spec.type_id == TABULAR_TABLE_WINDOW_NODE_TYPE_ID
    assert table_spec.display_name == "Table Filter"
    assert (
        {port.key: port.data_type for port in table_spec.ports}["window"]
        == TABULAR_WINDOW_REF_TYPE_ID
    )
    assert {prop.key: prop.default for prop in table_spec.properties} == {
        "row_offset": 0,
        "row_limit": 1000,
        "column_offset": 0,
        "column_limit": 0,
        "columns": "",
    }
    assert all(not prop.inspector_visible for prop in table_spec.properties)

    assert array_spec.type_id == TABULAR_ARRAY_SLICE_2D_NODE_TYPE_ID
    assert (
        {port.key: port.data_type for port in array_spec.ports}["slice_2d"]
        == ARRAY_SLICE_2D_REF_TYPE_ID
    )
    assert {prop.key: prop.default for prop in array_spec.properties} == {
        "row_offset": 0,
        "row_limit": 1000,
        "column_offset": 0,
        "column_limit": 100,
    }
    assert all(not prop.inspector_visible for prop in array_spec.properties)

    assert table_writer_spec.type_id == TABULAR_WRITE_TABLE_WINDOW_NODE_TYPE_ID
    assert table_writer_spec.display_name == "Write Filtered Table"
    assert table_writer_spec.properties[0].file_filter == TABULAR_TABLE_OUTPUT_FILES_FILTER
    assert table_writer_spec.properties[0].default == ""
    assert all(
        port.data_access == "tree"
        for port in table_writer_spec.ports
        if port.direction == "in"
    )
    assert table_materializer_spec.display_name == "Materialize Filtered Table"
    rows_port = next(port for port in table_materializer_spec.ports if port.key == "rows")
    assert rows_port.data_type == GRAPH_DICTIONARY_DATA_TYPE_ID
    assert rows_port.data_access == "list"
    values_port = next(port for port in array_materializer_spec.ports if port.key == "values")
    assert values_port.data_type == GRAPH_ARRAY_DATA_TYPE_ID
    assert values_port.data_access == "list"
    assert array_writer_spec.type_id == TABULAR_WRITE_ARRAY_SLICE_2D_NODE_TYPE_ID
    assert array_writer_spec.properties[0].file_filter == TABULAR_ARRAY_OUTPUT_FILES_FILTER
    assert array_writer_spec.properties[0].default == ""
    assert all(
        port.data_access == "tree"
        for port in array_writer_spec.ports
        if port.direction == "in"
    )
    assert next(port for port in table_materializer_spec.ports if port.key == "window").data_access == "item"


def test_property_adapter_projects_friendly_table_and_array_extraction_rows() -> None:
    [adapter] = create_tabular_property_edit_adapters()
    table_node = SimpleNamespace(
        type_id=TABULAR_TABLE_WINDOW_NODE_TYPE_ID,
        properties={
            "row_offset": 0,
            "row_limit": 0,
            "column_offset": 0,
            "column_limit": 0,
            "columns": "station,temp",
        },
    )
    table_items = {
        item["key"]: item
        for item in adapter.build_property_items(PropertyEditAdapterContext(node=table_node), [])
    }

    assert table_items["table_window_columns"]["editor_mode"] == "chip_list"
    assert table_items["table_window_columns"]["value"] == ["station", "temp"]
    assert table_items["table_window_row_count"]["help_text"] == "Enter 0 for all remaining rows."
    assert table_items["table_window_summary"]["editor_mode"] == "summary"
    assert "Rows 1 onward" in table_items["table_window_summary"]["value"]

    rewrite = adapter.rewrite_property_edit(
        PropertyEditAdapterContext(node=table_node),
        key="table_window_column_start",
        value="C",
    )
    assert rewrite is not None
    assert rewrite.key == "column_offset"
    assert rewrite.value == 2

    array_node = SimpleNamespace(
        type_id=TABULAR_ARRAY_SLICE_2D_NODE_TYPE_ID,
        properties={"row_offset": 1, "row_limit": 2, "column_offset": 0, "column_limit": 0},
    )
    array_items = {
        item["key"]: item
        for item in adapter.build_property_items(PropertyEditAdapterContext(node=array_node), [])
    }
    assert array_items["array_slice_2d_column_count"]["value"] == 0
    assert array_items["array_slice_2d_summary"]["editor_mode"] == "summary"
    assert "Columns A onward" in array_items["array_slice_2d_summary"]["value"]


def test_visible_export_helpers_write_bounded_table_and_array_rows(tmp_path: Path) -> None:
    table_output = tmp_path / "visible.csv"
    write_table_rows_to_path(
        table_output,
        columns=("station", "temp"),
        rows=(
            {"station": "S2", "temp": "22.0", "unused": "ignored"},
            {"station": "S1", "temp": "21.0", "unused": "ignored"},
        ),
    )
    assert table_output.read_text(encoding="utf-8").splitlines() == [
        "station,temp",
        "S2,22.0",
        "S1,21.0",
    ]

    jsonl_output = tmp_path / "visible.jsonl"
    write_table_rows_to_path(
        jsonl_output,
        columns=("station", "temp"),
        rows=({"station": "S2", "temp": "22.0", "unused": "ignored"},),
    )
    assert jsonl_output.read_text(encoding="utf-8").splitlines() == [
        '{"station": "S2", "temp": "22.0"}'
    ]

    array_output = tmp_path / "visible_array.tsv"
    write_array_rows_to_path(array_output, rows=((1, 2, 3), (4, 5, 6)))
    assert array_output.read_text(encoding="utf-8").splitlines() == [
        "1\t2\t3",
        "4\t5\t6",
    ]


def test_table_window_ref_full_limit_loads_all_remaining_rows_and_selected_columns(tmp_path: Path) -> None:
    table_ref = _table_ref(tmp_path)

    result = execute_table_filter(
        _context(
            inputs={"table_data": table_ref},
            properties={
                "row_offset": 1,
                "row_limit": 0,
                "column_offset": 0,
                "column_limit": 0,
                "columns": "temp, pressure",
            },
        )
    )

    window_ref = result.outputs["window"]
    assert isinstance(window_ref, TabularWindowRef)
    assert window_ref.row_limit == 0
    assert window_ref.column_limit == 0
    assert window_ref.columns == ("temp", "pressure")
    window = load_table_window(window_ref)
    assert window.columns == ("temp", "pressure")
    assert window.rows == ({"temp": 22.0, "pressure": 101},)


def test_array_slice_ref_full_limit_loads_all_remaining_values(tmp_path: Path) -> None:
    array_ref = _array_ref(tmp_path)

    result = execute_array_slice_2d(
        _context(
            inputs={"array_data": array_ref},
            properties={"row_offset": 1, "row_limit": 0, "column_offset": 2, "column_limit": 0},
        )
    )

    slice_ref = result.outputs["slice_2d"]
    assert isinstance(slice_ref, ArraySlice2DRef)
    assert slice_ref.row_limit == 0
    assert slice_ref.column_limit == 0
    loaded = load_array_slice_2d(slice_ref)
    assert loaded.values == ((6, 7), (10, 11))


def test_table_window_writer_exports_csv_and_materializer_warns_for_unbounded_ref(tmp_path: Path) -> None:
    table_ref = _table_ref(tmp_path)
    window_ref = execute_table_filter(
        _context(
            inputs={"table_data": table_ref},
            properties={"row_offset": 0, "row_limit": 0, "column_offset": 0, "column_limit": 0, "columns": ""},
        )
    ).outputs["window"]
    output = tmp_path / "window.csv"

    write_result = execute_write_table_filter(
        _context(inputs={"window": window_ref}, properties={"path": str(output)})
    )

    assert write_result.outputs["written_path"] == str(output)
    assert output.read_text(encoding="utf-8").splitlines() == [
        "station,temp,pressure",
        "A,21.5,100",
        "B,22.0,101",
    ]

    materialized = execute_materialize_table_filter(
        _context(inputs={"window": window_ref})
    )
    assert materialized.outputs["rows"] == [
        {"station": "A", "temp": 21.5, "pressure": 100},
        {"station": "B", "temp": 22.0, "pressure": 101},
    ]
    assert materialized.warnings


def test_array_slice_writer_exports_csv_and_npy(tmp_path: Path) -> None:
    numpy = pytest.importorskip("numpy")
    array_ref = _array_ref(tmp_path)
    slice_ref = execute_array_slice_2d(
        _context(
            inputs={"array_data": array_ref},
            properties={"row_offset": 0, "row_limit": 2, "column_offset": 1, "column_limit": 2},
        )
    ).outputs["slice_2d"]
    csv_output = tmp_path / "slice.csv"
    npy_output = tmp_path / "slice.npy"

    execute_write_array_slice_2d(
        _context(inputs={"slice_2d": slice_ref}, properties={"path": str(csv_output)})
    )
    execute_write_array_slice_2d(
        _context(inputs={"slice_2d": slice_ref}, properties={"path": str(npy_output)})
    )

    assert csv_output.read_text(encoding="utf-8").splitlines() == ["1,2", "5,6"]
    assert numpy.load(npy_output).tolist() == [[1, 2], [5, 6]]


def test_table_writer_blank_path_creates_managed_csv_artifact(tmp_path: Path) -> None:
    table_ref = _table_ref(tmp_path)
    window_ref = execute_table_filter(
        _context(
            inputs={"table_data": table_ref},
            properties={"row_offset": 0, "row_limit": 1, "column_offset": 0, "column_limit": 2, "columns": ""},
        )
    ).outputs["window"]
    project_path = tmp_path / "project.cxproj"
    runtime_snapshot = RuntimeSnapshot(schema_version=1, project_id="project_demo", metadata={})
    artifact_store = ProjectArtifactStore.from_project_metadata(
        project_path=project_path,
        project_metadata=runtime_snapshot.metadata,
    )
    runtime_snapshot_context = RuntimeSnapshotContext.from_snapshot(
        runtime_snapshot,
        project_path=str(project_path),
        artifact_store=artifact_store,
    )
    resolver = ProjectArtifactResolver(project_path=project_path, artifact_store=artifact_store)

    result = execute_write_table_filter(
        _context(
            inputs={"window": window_ref},
            properties={"path": ""},
            project_path=str(project_path),
            runtime_snapshot=runtime_snapshot,
            runtime_snapshot_context=runtime_snapshot_context,
            path_resolver=resolver.resolve_to_path,
            node_type_id=TABULAR_WRITE_TABLE_WINDOW_NODE_TYPE_ID,
        )
    )

    written_ref = result.outputs["written_path"]
    assert isinstance(written_ref, RuntimeArtifactRef)
    assert written_ref.data_type_id == PATH_DATA_TYPE_ID
    assert written_ref.schema_version == 1
    assert written_ref.format == "csv"
    assert written_ref.metadata == {}
    staged_path = resolver.resolve_to_path(written_ref.ref)
    assert staged_path is not None
    assert staged_path.read_text(encoding="utf-8").splitlines() == ["station,temp", "A,21.5"]
