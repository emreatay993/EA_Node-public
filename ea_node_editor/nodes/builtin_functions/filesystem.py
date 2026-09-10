# Purpose: Hold inert decorated source for ordinary filesystem built-ins.
# Map: feature_routes/core_integrations_file_process_email_spreadsheet.md
# Tests: tests/test_filesystem_function_nodes.py

SOURCE = r'''import corex

from ea_node_editor.nodes.builtins.filesystem import (
    execute_combine_file_paths,
    execute_construct_file_path,
    execute_contents_in_directory,
    execute_create_directory,
    execute_deconstruct_file_path,
    execute_delete_file,
    execute_move_file,
    execute_temporary_file_path,
)


def _result(ctx, result, code):
    for warning in result.warnings:
        ctx.warn(warning, code=code)
    return dict(result.outputs)


@corex.node(id="io.combine_file_paths", name="Combine File Paths", category=("Utilities", "File System"), icon="account_tree", description="Combines path segments using the host file system's path rules.", keywords=("path", "combine", "join", "file system"))
@corex.input("paths", value_type="COREX.DataTypes.Path", _accepted_data_types=("COREX.DataTypes.String",), structure="list", required=True, label="Paths", description="Ordered path segments to combine.")
@corex.output("final_path", value_type="COREX.DataTypes.Path", label="Final path", description="Combined file-system path.")
def combine_file_paths(ctx, paths):
    return _result(ctx, execute_combine_file_paths(ctx), "combine_file_paths")


@corex.node(id="io.construct_file_path", name="Construct File Path", category=("Utilities", "File System"), icon="account_tree", description="Constructs a file path from a directory, file name, and extension.", keywords=("path", "construct", "file name", "extension"))
@corex.path("directory", default="", label="Directory", port=True, _inline_editor="", _port_accepted_data_types=("COREX.DataTypes.String",), _port_description="Directory containing the file.", _port_label="Directory", _port_required=True, _port_structure="item", _port_value_type="COREX.DataTypes.Path")
@corex.text("file_name", default="", label="File name", port=True, _inline_editor="", _port_description="File name without the extension.", _port_label="File name", _port_required=True, _port_structure="item", _port_value_type="COREX.DataTypes.String")
@corex.text("file_extension", default="", label="File extension", port=True, _inline_editor="", _port_allow_empty_string=True, _port_description="File extension, with or without a leading dot; an empty extension is valid.", _port_label="File extension", _port_required=True, _port_structure="item", _port_value_type="COREX.DataTypes.String")
@corex.output("file_path", value_type="COREX.DataTypes.Path", label="File path", description="Constructed file path.")
def construct_file_path(ctx, settings):
    return _result(ctx, execute_construct_file_path(ctx), "construct_file_path")


@corex.node(id="io.deconstruct_file_path", name="Deconstruct File Path", category=("Utilities", "File System"), icon="account_tree", description="Splits a file path into its directory, file name, and extension.", keywords=("path", "deconstruct", "split", "extension"))
@corex.path("file_path", default="", label="File path", port=True, _inline_editor="", _port_accepted_data_types=("COREX.DataTypes.String",), _port_description="File path to split.", _port_label="File path", _port_required=True, _port_structure="item", _port_value_type="COREX.DataTypes.Path")
@corex.output("directory", value_type="COREX.DataTypes.Path", label="Directory", description="Directory portion of the path.")
@corex.output("file_name", value_type="COREX.DataTypes.String", label="File name", description="Final file name without its extension.")
@corex.output("file_extension", value_type="COREX.DataTypes.String", label="File extension", description="Final extension including its leading dot.")
def deconstruct_file_path(ctx, settings):
    return _result(ctx, execute_deconstruct_file_path(ctx), "deconstruct_file_path")


@corex.node(id="io.contents_in_directory", name="Contents in Directory", category=("Utilities", "File System"), icon="integrations/folder.svg", description="Lists matching files or directories to a bounded depth.", keywords=("directory", "contents", "files", "folders", "search"))
@corex.path("directory", default="", label="Directory", port=True, _inline_editor="", _port_accepted_data_types=("COREX.DataTypes.String",), _port_description="Directory to search; blank uses the saved project's parent or the worker directory.", _port_label="Directory", _port_required=False, _port_structure="item", _port_value_type="COREX.DataTypes.Path")
@corex.text("search_pattern", default="*", label="Search pattern", port=True, _inline_editor="", _port_description="Literal-name pattern supporting * and ? wildcards.", _port_label="Search pattern", _port_required=True, _port_structure="item", _port_value_type="COREX.DataTypes.String")
@corex.number("subdirectory_levels", default=0, minimum=0, maximum=10, step=1, label="Subdirectory levels", port=True, _inline_editor="slider", _port_description="Maximum subdirectory depth from 0 through 10.", _port_label="Subdirectory levels", _port_required=False, _port_structure="item", _port_value_type="COREX.DataTypes.Int")
@corex.dropdown("content_type", default=0, options=("Files", "Directories", "Files and Directories"), codes=(0, 1, 2), label="Content type", port=True, _port_description="Choose files, directories, or both.", _port_label="Content type", _port_required=False, _port_structure="item", _port_value_type="COREX.DataTypes.Int")
@corex.output("content_paths", value_type="COREX.DataTypes.Path", structure="list", label="Content paths", description="Sorted absolute paths for matching contents.")
def contents_in_directory(ctx, settings):
    return _result(ctx, execute_contents_in_directory(ctx), "contents_in_directory")


@corex.node(id="io.create_directory", name="Create Directory", category=("Utilities", "File System"), icon="create_new_folder", description="Creates a directory, optionally including missing parents.", keywords=("directory", "create", "folder", "recursive"))
@corex.path("directory", default="", label="Directory", port=True, _inline_editor="", _port_accepted_data_types=("COREX.DataTypes.String",), _port_description="Directory to create.", _port_label="Directory", _port_required=True, _port_structure="item", _port_value_type="COREX.DataTypes.Path")
@corex.switch("create_recursive", default=False, label="Create recursive", port=True, _port_description="Create missing parent directories.", _port_label="Create recursive", _port_required=False, _port_structure="item", _port_value_type="COREX.DataTypes.Bool")
@corex.output("created_directory", value_type="COREX.DataTypes.Path", label="Directory", description="Created or existing directory path.")
def create_directory(ctx, settings):
    return _result(ctx, execute_create_directory(ctx), "create_directory")


@corex.node(id="io.move_file", name="Move File", category=("Utilities", "File System"), icon="drive_file_move", description="Copies or moves a file to a destination path.", keywords=("file", "copy", "move", "overwrite"))
@corex.path("source_path", default="", label="Source path", port=True, _inline_editor="", _port_accepted_data_types=("COREX.DataTypes.String",), _port_description="Existing source file.", _port_label="Source path", _port_required=True, _port_structure="item", _port_value_type="COREX.DataTypes.Path")
@corex.path("target_path", default="", label="Target path", port=True, _inline_editor="", _port_accepted_data_types=("COREX.DataTypes.String",), _port_description="Existing target directory or destination file path.", _port_label="Target path", _port_required=True, _port_structure="item", _port_value_type="COREX.DataTypes.Path")
@corex.dropdown("operation_mode", default=0, options=("Copy", "Move"), codes=(0, 1), label="Operation mode", port=True, _port_description="Copy or move the source file.", _port_label="Operation mode", _port_required=False, _port_structure="item", _port_value_type="COREX.DataTypes.Int")
@corex.switch("overwrite_target_file", default=False, label="Overwrite target file", port=True, _port_description="Allow replacement of an existing destination file.", _port_label="Overwrite target file", _port_required=False, _port_structure="item", _port_value_type="COREX.DataTypes.Bool")
@corex.output("successful", value_type="COREX.DataTypes.Bool", label="Successful", description="True when the copy or move completed.")
def move_file(ctx, settings):
    return _result(ctx, execute_move_file(ctx), "move_file")


@corex.node(id="io.delete_file", name="Delete File", category=("Utilities", "File System"), icon="delete", description="Deletes a regular file.", keywords=("file", "delete", "remove"))
@corex.path("file_path", default="", label="File path", port=True, _inline_editor="", _port_accepted_data_types=("COREX.DataTypes.String",), _port_description="Regular file to delete.", _port_label="File path", _port_required=True, _port_structure="item", _port_value_type="COREX.DataTypes.Path")
@corex.output("successful", value_type="COREX.DataTypes.Bool", label="Successful", description="True when the file was deleted.")
def delete_file(ctx, settings):
    return _result(ctx, execute_delete_file(ctx), "delete_file")


@corex.node(id="io.temporary_file_path", name="Temporary File Path", category=("Utilities", "File System"), icon="description", description="Returns an unreserved path in the operating system temporary directory.", keywords=("temporary", "file", "path", "random"))
@corex.text("file_name", default="", label="File name", port=True, _inline_editor="", _port_description="Optional file name; blank generates a random name.", _port_label="File name", _port_required=False, _port_structure="item", _port_value_type="COREX.DataTypes.String")
@corex.text("file_extension", default="", label="File extension", port=True, _inline_editor="", _port_description="Optional extension, with or without a leading dot; blank generates one.", _port_label="File extension", _port_required=False, _port_structure="item", _port_value_type="COREX.DataTypes.String")
@corex.output("file_path", value_type="COREX.DataTypes.Path", label="File path", description="Unreserved temporary file path.")
def temporary_file_path(ctx, settings):
    return _result(ctx, execute_temporary_file_path(ctx), "temporary_file_path")
'''

__all__ = ["SOURCE"]
