# Purpose: Hold inert decorated source for ordinary file and image integrations.
# Map: feature_routes/core_integrations_file_process_email_spreadsheet.md
# Tests: tests/test_integrations_track_f.py

SOURCE = r"""import corex

from ea_node_editor.nodes.builtins.integrations_file_io import (
    execute_file_read,
    execute_file_write,
    execute_image_export,
    execute_image_import,
)


@corex.node(
    id="io.file_read",
    _solution_reuse_scope="session",
    name="File Read",
    category=("Input / Output",),
    icon="integrations/description.svg",
    description="Reads a UTF-8 text file into a string output.",
    keywords=("file", "read", "text"),
)
@corex.path(
    "path",
    default="",
    label="File Path",
    file_filter="Text/Data Files (*.txt *.md *.csv *.json *.jsonl *.yaml *.yml *.log);;All Files (*)",
    port=True,
    _inline_editor="",
    _port_accepted_data_types=(),
    _port_description="File path to read; overrides the configured File Path property when connected.",
    _port_label="",
    _port_required=True,
    _port_structure="item",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.output(
    "text",
    value_type="COREX.DataTypes.String",
    label="",
    description="UTF-8 text read from the file.",
)
def file_read(ctx, settings):
    result = execute_file_read(ctx)
    for warning in result.warnings:
        ctx.warn(warning, code="file_read")
    return dict(result.outputs)


@corex.node(
    id="io.file_write",
    name="File Write",
    category=("Input / Output",),
    icon="integrations/save.svg",
    description="Writes text or JSON-compatible data to a chosen or managed output file.",
    keywords=("file", "write", "json"),
)
@corex.path(
    "path",
    default="output.txt",
    label="Output Path",
    file_filter="Text/Data Files (*.txt *.md *.csv *.json *.jsonl *.yaml *.yml *.log);;All Files (*)",
    port=True,
    _inline_editor="",
    _port_accepted_data_types=(),
    _port_description="Optional output path; a managed output is created when empty.",
    _port_label="",
    _port_required=False,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.input(
    "text",
    value_type="COREX.DataTypes.String",
    structure="tree",
    required=False,
    label="",
    description="Text content to write when JSON serialization is disabled.",
)
@corex.input(
    "data",
    value_type="COREX.DataTypes.JsonValue",
    structure="tree",
    required=False,
    label="",
    description="JSON-compatible value to serialize when JSON output is enabled.",
)
@corex.output(
    "written_path",
    value_type="COREX.DataTypes.Path",
    label="",
    description="Path or managed artifact reference for the written file.",
)
@corex.switch(
    "as_json",
    default=False,
    label="Serialize As JSON",
    _inline_editor="",
)
def file_write(ctx, text, data, settings):
    result = execute_file_write(ctx)
    for warning in result.warnings:
        ctx.warn(warning, code="file_write")
    return dict(result.outputs)


@corex.node(
    id="io.image_import",
    _solution_reuse_scope="session",
    name="Import Image",
    category=("Input / Output",),
    icon="integrations/download.svg",
    description="Loads a validated PNG file into an in-memory COREX Image.",
    keywords=("image", "import", "png"),
)
@corex.path(
    "path",
    default="",
    label="PNG Path",
    file_filter="PNG Image (*.png)",
    port=True,
    _inline_editor="",
    _port_accepted_data_types=(),
    _port_label="",
    _port_description="Path of the PNG file to import.",
    _port_required=True,
    _port_structure="item",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.output(
    "image",
    value_type=corex.Image,
    label="",
    description="Imported image.",
)
def image_import(ctx, settings):
    result = execute_image_import(ctx)
    for warning in result.warnings:
        ctx.warn(warning, code="image_import")
    return dict(result.outputs)


@corex.node(
    id="io.image_export",
    name="Export Image",
    category=("Input / Output",),
    icon="integrations/download.svg",
    description="Writes an in-memory COREX Image to a PNG file.",
    keywords=("image", "export", "png"),
)
@corex.input(
    "image",
    value_type=corex.Image,
    structure="tree",
    required=True,
    label="",
    description="Image tree to export.",
)
@corex.path(
    "path",
    default="",
    label="PNG Path",
    file_filter="PNG Image (*.png)",
    port=True,
    _inline_editor="",
    _port_accepted_data_types=(),
    _port_label="",
    _port_description="Destination path for each exported PNG image.",
    _port_required=True,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.Path",
)
@corex.switch(
    "overwrite",
    default=True,
    label="Overwrite",
    port=True,
    _inline_editor="",
    _port_label="",
    _port_description="Whether existing image files may be overwritten.",
    _port_required=False,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.Bool",
)
@corex.output(
    "written_path",
    value_type="COREX.DataTypes.Path",
    label="",
    description="Path written for the exported image.",
)
def image_export(ctx, image, settings):
    result = execute_image_export(ctx)
    for warning in result.warnings:
        ctx.warn(warning, code="image_export")
    return dict(result.outputs)
"""

__all__ = ["SOURCE"]
