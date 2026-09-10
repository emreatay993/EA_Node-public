# Purpose: Hold inert decorated source for the Tabular Data add-on's ordinary nodes.
# Map: feature_routes/tabular_data_addon_preview.md
# Tests: tests/test_tabular_input_node.py, tests/test_tabular_extraction_nodes.py, tests/test_tabular_function_migration.py

SOURCE = r'''import corex

from ea_node_editor.addons.tabular_data.extraction_nodes import (
    execute_array_slice_2d,
    execute_materialize_array_slice_2d,
    execute_materialize_table_filter,
    execute_table_filter,
    execute_write_array_slice_2d,
    execute_write_table_filter,
)
from ea_node_editor.addons.tabular_data.input_node import execute_tabular_input


@corex.node(
    id="tabular.input",
    _solution_reuse_scope="session",
    name="Tabular Data Input",
    category=("Data",),
    icon="integrations/tabular_data.svg",
    description="Creates lazy table or dense-array references from a tabular data file.",
    keywords=("tabular", "csv", "array"),
)
@corex.path(
    "path",
    default="",
    label="Path",
    file_filter="Tabular Data (*.csv *.tsv *.txt *.xlsx *.xlsm *.parquet *.h5 *.hdf *.hdf5 *.npy *.npz);;All Files (*)",
    port=True,
    _inline_editor="",
    _inspector_editor="path",
    _port_accepted_data_types=(),
    _port_description="Path to a CSV, spreadsheet, or supported array source.",
    _port_required=True,
    _property_group="Source",
)
@corex.output(
    "table_data",
    value_type="COREX.Runtime.TabularDataRef",
    label="Table Data",
    description="Lazy reference to row-oriented tabular data.",
)
@corex.output(
    "array_data",
    value_type="COREX.Runtime.ArrayDataRef",
    label="Array Data",
    description="Lazy reference to dense multidimensional array data.",
)
@corex.text(
    "delimiter",
    default="",
    label="Delimiter",
    _inline_editor="",
    _inspector_editor="text",
    _property_group="Text Parsing",
)
@corex.text(
    "encoding",
    default="utf-8",
    label="Encoding",
    _inline_editor="",
    _inspector_editor="text",
    _property_group="Text Parsing",
)
@corex.number(
    "header_row",
    default=0,
    label="Header Row",
    _inline_editor="",
    _inspector_editor="text",
    _property_group="Text Parsing",
    _property_type="json",
)
@corex.number(
    "skip_rows",
    default=0,
    label="Skip Rows",
    _inline_editor="",
    _inspector_editor="text",
    _property_group="Text Parsing",
)
@corex.text_area(
    "schema_hints",
    default="",
    label="Schema Hints",
    _inline_editor="",
    _inspector_editor="textarea",
    _property_default={},
    _property_group="Text Parsing",
    _property_type="json",
)
@corex.text(
    "selected_object",
    default="",
    label="Data Source",
    _inline_editor="",
    _inspector_editor="text",
    _property_group="Selection",
)
@corex.text(
    "array_slice_2d",
    default="",
    label="Selected 2D Array Slice",
    _inline_editor="",
    _inspector_visible=False,
    _property_default={
        "row_offset": 0,
        "column_offset": 0,
        "row_limit": 50,
        "column_limit": 50,
    },
    _property_group="Selection",
    _property_type="json",
)
@corex.text(
    "tabular_selected_columns",
    default="",
    label="Selected Columns",
    _inline_editor="",
    _inspector_visible=False,
    _property_default=[],
    _property_group="Selection",
    _property_type="json",
)
@corex.dropdown(
    "cache_policy",
    default="app_managed_parquet",
    options=("app_managed_parquet", "source_direct"),
    label="Cache Policy",
    _inline_editor="",
    _inspector_editor="enum",
    _property_group="Cache",
)
@corex.switch(
    "project_managed_source",
    default=False,
    label="Project-Managed Source",
    _inline_editor="",
    _inspector_editor="toggle",
    _property_group="Portability",
)
@corex.switch(
    "project_managed_cache",
    default=False,
    label="Project-Managed Cache",
    _inline_editor="",
    _inspector_editor="toggle",
    _property_group="Portability",
)
@corex.switch(
    "allow_npz_archive_preview",
    default=False,
    label="Allow NPZ Archive Preview",
    _inline_editor="",
    _inspector_editor="toggle",
    _property_group="Safety",
)
@corex.text(
    "tabular_table_view_state",
    default="",
    label="Tabular Table View State",
    _inline_editor="",
    _inspector_visible=False,
    _property_default={},
    _property_type="json",
)
def tabular_input(ctx, settings):
    result = execute_tabular_input(ctx)
    for warning in result.warnings:
        ctx.warn(warning, code="tabular_runtime")
    return dict(result.outputs)


@corex.node(
    id="tabular.table_filter",
    _solution_reuse_scope="session",
    name="Table Filter",
    category=("Data",),
    icon="integrations/tabular_data.svg",
    description="Creates a lazy filtered-table reference from tabular data.",
    keywords=("table", "filter", "window"),
)
@corex.input(
    "table_data",
    value_type="COREX.Runtime.TabularDataRef",
    required=True,
    label="Table Data",
    description="Lazy tabular source to filter by row, column, and selection settings.",
)
@corex.number(
    "row_offset",
    default=0,
    label="Row Offset",
    _inline_editor="",
    _inspector_visible=False,
    _property_group="Selection",
)
@corex.number(
    "row_limit",
    default=1000,
    label="Row Limit",
    _inline_editor="",
    _inspector_visible=False,
    _property_group="Selection",
)
@corex.number(
    "column_offset",
    default=0,
    label="Column Offset",
    _inline_editor="",
    _inspector_visible=False,
    _property_group="Selection",
)
@corex.number(
    "column_limit",
    default=0,
    label="Column Limit",
    _inline_editor="",
    _inspector_visible=False,
    _property_group="Selection",
)
@corex.text(
    "columns",
    default="",
    label="Columns",
    _inline_editor="",
    _inspector_visible=False,
    _property_group="Selection",
)
@corex.output(
    "window",
    value_type="COREX.Runtime.TabularWindowRef",
    label="Window",
    description="Lazy reference to the selected table window.",
)
def table_filter(ctx, table_data, settings):
    result = execute_table_filter(ctx)
    for warning in result.warnings:
        ctx.warn(warning, code="tabular_runtime")
    return dict(result.outputs)


@corex.node(
    id="tabular.array_slice_2d",
    _solution_reuse_scope="session",
    name="Array Slice 2D",
    category=("Data",),
    icon="integrations/tabular_data.svg",
    description="Creates a lazy 2D array-slice reference from array data.",
    keywords=("array", "slice", "2d"),
)
@corex.input(
    "array_data",
    value_type="COREX.Runtime.ArrayDataRef",
    required=True,
    label="Array Data",
    description="Lazy dense-array source to slice by row and column bounds.",
)
@corex.number(
    "row_offset",
    default=0,
    label="Row Offset",
    _inline_editor="",
    _inspector_visible=False,
    _property_group="Selection",
)
@corex.number(
    "row_limit",
    default=1000,
    label="Row Limit",
    _inline_editor="",
    _inspector_visible=False,
    _property_group="Selection",
)
@corex.number(
    "column_offset",
    default=0,
    label="Column Offset",
    _inline_editor="",
    _inspector_visible=False,
    _property_group="Selection",
)
@corex.number(
    "column_limit",
    default=100,
    label="Column Limit",
    _inline_editor="",
    _inspector_visible=False,
    _property_group="Selection",
)
@corex.output(
    "slice_2d",
    value_type="COREX.Runtime.ArraySlice2DRef",
    label="Slice 2D",
    description="Lazy reference to the selected two-dimensional array slice.",
)
def array_slice_2d(ctx, array_data, settings):
    result = execute_array_slice_2d(ctx)
    for warning in result.warnings:
        ctx.warn(warning, code="tabular_runtime")
    return dict(result.outputs)


@corex.node(
    id="tabular.write_table_filter",
    name="Write Filtered Table",
    category=("Data",),
    icon="integrations/tabular_data.svg",
    description="Exports a lazy filtered table without materializing it as a list first.",
    keywords=("table", "export", "csv"),
)
@corex.input(
    "window",
    value_type="COREX.Runtime.TabularWindowRef",
    structure="tree",
    required=True,
    label="Window",
    description="Lazy filtered-table window to export.",
)
@corex.path(
    "path",
    default="",
    label="Output Path",
    file_filter="Table Output (*.csv *.tsv *.txt *.jsonl *.xlsx *.xlsm);;All Files (*)",
    port=True,
    _inspector_editor="path",
    _port_accepted_data_types=(),
    _port_description="Optional output path; a managed CSV is created when empty.",
    _port_label="Path",
    _port_required=False,
    _port_structure="tree",
    _property_group="Output",
)
@corex.output(
    "written_path",
    value_type="COREX.DataTypes.Path",
    label="",
    description="Path or managed artifact reference for the exported table.",
)
def write_table_filter(ctx, window, settings):
    result = execute_write_table_filter(ctx)
    for warning in result.warnings:
        ctx.warn(warning, code="tabular_runtime")
    return dict(result.outputs)


@corex.node(
    id="tabular.write_array_slice_2d",
    name="Write Array Slice 2D",
    category=("Data",),
    icon="integrations/tabular_data.svg",
    description="Exports a lazy 2D array slice without materializing it through a script.",
    keywords=("array", "slice", "export"),
)
@corex.input(
    "slice_2d",
    value_type="COREX.Runtime.ArraySlice2DRef",
    structure="tree",
    required=True,
    label="Slice 2D",
    description="Lazy two-dimensional array slice to export.",
)
@corex.path(
    "path",
    default="",
    label="Output Path",
    file_filter="Array Output (*.csv *.tsv *.txt *.xlsx *.xlsm *.npy);;All Files (*)",
    port=True,
    _inspector_editor="path",
    _port_accepted_data_types=(),
    _port_description="Optional output path; a managed CSV is created when empty.",
    _port_label="Path",
    _port_required=False,
    _port_structure="tree",
    _property_group="Output",
)
@corex.output(
    "written_path",
    value_type="COREX.DataTypes.Path",
    label="",
    description="Path or managed artifact reference for the exported array slice.",
)
def write_array_slice_2d(ctx, slice_2d, settings):
    result = execute_write_array_slice_2d(ctx)
    for warning in result.warnings:
        ctx.warn(warning, code="tabular_runtime")
    return dict(result.outputs)


@corex.node(
    id="tabular.materialize_table_filter",
    _solution_reuse_scope="session",
    name="Materialize Filtered Table",
    category=("Data",),
    icon="integrations/tabular_data.svg",
    description="Loads a filtered table into memory as list[dict] for scripts and debugging.",
    keywords=("table", "materialize", "rows"),
)
@corex.input(
    "window",
    value_type="COREX.Runtime.TabularWindowRef",
    required=True,
    label="Window",
    description="Lazy filtered-table window to materialize.",
)
@corex.output(
    "rows",
    value_type="COREX.DataTypes.GraphDictionary",
    structure="list",
    label="Rows",
    description="Materialized table rows represented as dictionaries.",
)
def materialize_table_filter(ctx, window):
    result = execute_materialize_table_filter(ctx)
    for warning in result.warnings:
        ctx.warn(warning, code="tabular_runtime")
    return dict(result.outputs)


@corex.node(
    id="tabular.materialize_array_slice_2d",
    _solution_reuse_scope="session",
    name="Materialize Array Slice 2D",
    category=("Data",),
    icon="integrations/tabular_data.svg",
    description="Loads a 2D array slice into memory as list[list] for scripts and debugging.",
    keywords=("array", "materialize", "values"),
)
@corex.input(
    "slice_2d",
    value_type="COREX.Runtime.ArraySlice2DRef",
    required=True,
    label="Slice 2D",
    description="Lazy two-dimensional array slice to materialize.",
)
@corex.output(
    "values",
    value_type="COREX.DataTypes.GraphArray",
    structure="list",
    label="Values",
    description="Materialized two-dimensional values represented as nested lists.",
)
def materialize_array_slice_2d(ctx, slice_2d):
    result = execute_materialize_array_slice_2d(ctx)
    for warning in result.warnings:
        ctx.warn(warning, code="tabular_runtime")
    return dict(result.outputs)
'''

__all__ = ["SOURCE"]
