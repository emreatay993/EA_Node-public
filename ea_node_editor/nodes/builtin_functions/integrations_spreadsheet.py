# Purpose: Hold inert decorated source for CSV and spreadsheet integrations.
# Map: feature_routes/core_integrations_file_process_email_spreadsheet.md
# Tests: tests/test_integrations_track_f.py

SOURCE = r"""import corex

from ea_node_editor.nodes.builtins.integrations_spreadsheet import (
    execute_excel_read,
    execute_excel_write,
)


@corex.node(
    id="io.excel_read",
    _solution_reuse_scope="session",
    name="Excel Read",
    category=("Input / Output",),
    icon="integrations/table_view.svg",
    description="Loads CSV or Excel worksheet rows as dictionaries keyed by column header.",
    keywords=("excel", "csv", "spreadsheet"),
)
@corex.path(
    "path",
    default="",
    label="File Path",
    file_filter="Spreadsheet Files (*.csv *.xlsx *.xlsm);;All Files (*)",
    port=True,
    _inline_editor="",
    _port_accepted_data_types=(),
    _port_description="CSV or Excel file path; overrides the configured File Path property.",
    _port_label="",
    _port_required=True,
    _port_structure="item",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.output(
    "rows",
    value_type="COREX.DataTypes.GraphDictionary",
    structure="list",
    label="",
    description="Worksheet rows represented as dictionaries keyed by normalized headers.",
)
@corex.text(
    "sheet_name",
    default="",
    label="Sheet Name",
    _inline_editor="",
)
def excel_read(ctx, settings):
    result = execute_excel_read(ctx)
    for warning in result.warnings:
        ctx.warn(warning, code="excel_read")
    return dict(result.outputs)


@corex.node(
    id="io.excel_write",
    name="Excel Write",
    category=("Input / Output",),
    icon="integrations/download.svg",
    description="Writes dictionary rows to a CSV or Excel workbook.",
    keywords=("excel", "csv", "export"),
)
@corex.input(
    "rows",
    value_type="COREX.DataTypes.GraphDictionary",
    structure="tree",
    required=True,
    label="",
    description="Dictionary rows to write using their keys as column headers.",
)
@corex.path(
    "path",
    default="output.csv",
    label="Output Path",
    file_filter="Spreadsheet Files (*.csv *.xlsx *.xlsm);;All Files (*)",
    port=True,
    _inline_editor="",
    _port_accepted_data_types=(),
    _port_description="Optional CSV or Excel output path; a managed CSV is created when empty.",
    _port_label="",
    _port_required=False,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.output(
    "written_path",
    value_type="COREX.DataTypes.Path",
    label="",
    description="Path or managed artifact reference for the written spreadsheet.",
)
def excel_write(ctx, rows, settings):
    result = execute_excel_write(ctx)
    for warning in result.warnings:
        ctx.warn(warning, code="excel_write")
    return dict(result.outputs)
"""

__all__ = ["SOURCE"]
