# Purpose: Execute built-in lexical and mutating filesystem operations.
# Map: feature_routes/core_integrations_file_process_email_spreadsheet.md
# Tests: tests/test_filesystem_nodes.py

from __future__ import annotations

import os
import re
import stat
import tempfile
import uuid
from collections.abc import Sequence
from pathlib import Path, PureWindowsPath
from typing import Any

from ea_node_editor.nodes.execution_context import (
    ExecutionContext,
    NodeInputNotReadyError,
    NodeResult,
)
from ea_node_editor.runtime_contracts import RuntimeArtifactRef


def _configured_value(ctx: ExecutionContext, key: str) -> Any:
    return ctx.inputs[key] if key in ctx.inputs else ctx.properties.get(key)


def _path_text(value: Any, *, label: str, allow_empty: bool = False) -> str:
    if isinstance(value, RuntimeArtifactRef):
        raise TypeError(f"{label} does not accept artifact references.")
    if not isinstance(value, (str, os.PathLike)):
        raise TypeError(f"{label} must be Text or Path.")
    text = os.fspath(value)
    if not isinstance(text, str):
        raise TypeError(f"{label} must be a text path.")
    if "\0" in text:
        raise ValueError(f"{label} must not contain a null character.")
    reference_text = text.strip()
    if (
        len(reference_text) >= 2
        and reference_text[0] == reference_text[-1]
        and reference_text[0] in "\"'"
    ):
        reference_text = reference_text[1:-1].strip()
    if reference_text.lower().startswith(("saved://", "temp://")):
        raise TypeError(f"{label} does not accept artifact references.")
    if not text and not allow_empty:
        raise NodeInputNotReadyError(f"{label} is required.")
    return text


def _required_path(ctx: ExecutionContext, key: str, label: str) -> str:
    value = _configured_value(ctx, key)
    if value is None:
        raise NodeInputNotReadyError(f"{label} is required.")
    return _path_text(value, label=label)


def _file_component(value: Any, *, label: str, allow_empty: bool = False) -> str:
    text = _path_text(value, label=label, allow_empty=allow_empty)
    if text and (os.path.basename(text) != text or text in (os.curdir, os.pardir)):
        raise ValueError(f"{label} must be a single path component.")
    if os.name == "nt" and text:
        if any(character in '<>:"/\\|?*' or ord(character) < 32 for character in text):
            raise ValueError(f"{label} contains a character that Windows filenames do not allow.")
        if text.endswith((" ", ".")):
            raise ValueError(f"{label} must not end with a space or dot on Windows.")
    return text


def _validate_final_file_name(file_name: str) -> None:
    if os.name == "nt" and PureWindowsPath(file_name).is_reserved():
        raise ValueError(f"File name is reserved on Windows: {file_name}")


def _resolved_path(ctx: ExecutionContext, value: Any, *, label: str) -> Path:
    text = _path_text(value, label=label)
    return (ctx.resolve_path_value(text) or Path(text)).absolute()


def _required_resolved_path(ctx: ExecutionContext, key: str, label: str) -> Path:
    value = _configured_value(ctx, key)
    if value is None:
        raise NodeInputNotReadyError(f"{label} is required.")
    return _resolved_path(ctx, value, label=label)


def _integer_setting(value: Any, *, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an Integer.")
    if not minimum <= value <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}.")
    return value


def _literal_pattern(pattern: str) -> re.Pattern[str]:
    expression = "".join(
        ".*" if character == "*" else "." if character == "?" else re.escape(character)
        for character in pattern
    )
    return re.compile(f"(?:{expression})\\Z", re.IGNORECASE if os.name == "nt" else 0)


def _entry_is_reparse_point(entry: os.DirEntry[str]) -> bool:
    entry_status = entry.stat(follow_symlinks=False)
    return stat.S_ISLNK(entry_status.st_mode) or bool(
        getattr(entry_status, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def execute_combine_file_paths(ctx: ExecutionContext) -> NodeResult:
    paths = _configured_value(ctx, "paths")
    if paths is None:
        raise NodeInputNotReadyError("Paths is required.")
    if isinstance(paths, (str, bytes, os.PathLike)) or not isinstance(paths, Sequence):
        raise TypeError("Paths must be a list of Text or Path values.")
    if not paths:
        raise ValueError("Paths must contain at least one path.")
    segments = [_path_text(value, label="Paths item", allow_empty=True) for value in paths]
    return NodeResult(outputs={"final_path": os.path.join(*segments)})


def execute_construct_file_path(ctx: ExecutionContext) -> NodeResult:
    directory = _required_path(ctx, "directory", "Directory")
    file_name_value = _configured_value(ctx, "file_name")
    if file_name_value is None:
        raise NodeInputNotReadyError("File name is required.")
    file_name = _file_component(
        file_name_value,
        label="File name",
    )
    extension_value = _configured_value(ctx, "file_extension")
    if extension_value is None:
        raise NodeInputNotReadyError("File extension is required.")
    extension = _file_component(
        extension_value,
        label="File extension",
        allow_empty=True,
    )
    if extension and not extension.startswith("."):
        extension = f".{extension}"
    final_file_name = file_name + extension
    _validate_final_file_name(final_file_name)
    return NodeResult(outputs={"file_path": os.path.join(directory, final_file_name)})


def execute_deconstruct_file_path(ctx: ExecutionContext) -> NodeResult:
    file_path = _required_path(ctx, "file_path", "File path")
    directory, final_component = os.path.split(file_path)
    file_name, file_extension = os.path.splitext(final_component)
    return NodeResult(
        outputs={
            "directory": directory,
            "file_name": file_name,
            "file_extension": file_extension,
        }
    )


def execute_contents_in_directory(ctx: ExecutionContext) -> NodeResult:
    directory_value = _configured_value(ctx, "directory")
    if directory_value is None or (
        isinstance(directory_value, (str, os.PathLike)) and not os.fspath(directory_value)
    ):
        directory = Path(ctx.project_path).absolute().parent if ctx.project_path else Path.cwd()
    else:
        directory = _resolved_path(ctx, directory_value, label="Directory")

    pattern_value = _configured_value(ctx, "search_pattern")
    pattern = "*" if pattern_value is None else _path_text(
        pattern_value, label="Search pattern", allow_empty=True
    )
    matcher = _literal_pattern(pattern)
    levels_value = _configured_value(ctx, "subdirectory_levels")
    levels = _integer_setting(
        0 if levels_value is None else levels_value,
        label="Subdirectory levels",
        minimum=0,
        maximum=10,
    )
    content_value = _configured_value(ctx, "content_type")
    content_type = _integer_setting(
        0 if content_value is None else content_value,
        label="Content type",
        minimum=0,
        maximum=2,
    )

    results: list[str] = []
    pending = [(directory, 0)]
    while pending:
        if ctx.should_stop():
            raise InterruptedError("run_stop_requested")
        current, depth = pending.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                if ctx.should_stop():
                    raise InterruptedError("run_stop_requested")
                path = Path(entry.path)
                is_directory = entry.is_dir()
                if matcher.fullmatch(entry.name) and (
                    content_type == 2
                    or (content_type == 1 and is_directory)
                    or (content_type == 0 and entry.is_file())
                ):
                    results.append(str(path.absolute()))
                if depth < levels and is_directory and not _entry_is_reparse_point(entry):
                    pending.append((path, depth + 1))
    return NodeResult(outputs={"content_paths": sorted(results, key=os.path.normcase)})


def execute_create_directory(ctx: ExecutionContext) -> NodeResult:
    directory_value = _configured_value(ctx, "directory")
    if directory_value is None:
        raise NodeInputNotReadyError("Directory is required.")
    directory = _resolved_path(ctx, directory_value, label="Directory")
    recursive_value = _configured_value(ctx, "create_recursive")
    recursive = False if recursive_value is None else recursive_value
    if not isinstance(recursive, bool):
        raise TypeError("Create recursive must be Boolean.")
    if ctx.should_stop():
        raise InterruptedError("run_stop_requested")
    directory.mkdir(parents=recursive, exist_ok=True)
    return NodeResult(outputs={"created_directory": str(directory)})


def execute_temporary_file_path(ctx: ExecutionContext) -> NodeResult:
    name_value = _configured_value(ctx, "file_name")
    extension_value = _configured_value(ctx, "file_extension")
    file_name = (
        uuid.uuid4().hex
        if name_value is None or name_value == ""
        else _file_component(name_value, label="File name")
    )
    extension = (
        uuid.uuid4().hex
        if extension_value is None or extension_value == ""
        else _file_component(extension_value, label="File extension")
    )
    if not extension.startswith("."):
        extension = f".{extension}"
    final_file_name = file_name + extension
    _validate_final_file_name(final_file_name)
    return NodeResult(outputs={"file_path": str(Path(tempfile.gettempdir(), final_file_name).absolute())})


def _operational_failure(message: str) -> NodeResult:
    return NodeResult(outputs={"successful": False}, warnings=(message,))


def _is_regular_unlinked_file(path: Path) -> bool:
    status = path.lstat()
    return stat.S_ISREG(status.st_mode) and not bool(
        getattr(status, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def execute_move_file(ctx: ExecutionContext) -> NodeResult:
    source = _required_resolved_path(ctx, "source_path", "Source path")
    target = _required_resolved_path(ctx, "target_path", "Target path")
    mode_value = _configured_value(ctx, "operation_mode")
    mode = _integer_setting(
        0 if mode_value is None else mode_value,
        label="Operation mode",
        minimum=0,
        maximum=1,
    )
    overwrite_value = _configured_value(ctx, "overwrite_target_file")
    overwrite = False if overwrite_value is None else overwrite_value
    if not isinstance(overwrite, bool):
        raise TypeError("Overwrite target file must be Boolean.")

    temporary_path: Path | None = None
    try:
        if not _is_regular_unlinked_file(source):
            return _operational_failure(f"Source path is not a regular file: {source}")
        if target.is_dir():
            if target.is_symlink() or not _is_safe_directory(target):
                return _operational_failure(f"Target directory is a link or reparse point: {target}")
            target = target / source.name
        if not target.parent.is_dir() or not _is_safe_directory(target.parent):
            return _operational_failure(f"Target parent directory does not exist or is unsafe: {target.parent}")
        if target.exists() or target.is_symlink():
            if target.is_dir() or not _is_regular_unlinked_file(target):
                return _operational_failure(f"Target path is not a regular file: {target}")
            if os.path.samefile(source, target):
                return _operational_failure(f"Source and target refer to the same file: {source}")
            if not overwrite:
                return _operational_failure(f"Target file already exists and overwrite is disabled: {target}")
        if ctx.should_stop():
            raise InterruptedError("run_stop_requested")

        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{target.name}.corex-tmp-", dir=target.parent
        )
        temporary_path = Path(temporary)
        with os.fdopen(descriptor, "wb") as output_stream:
            with source.open("rb") as input_stream:
                while chunk := input_stream.read(1024 * 1024):
                    if ctx.should_stop():
                        raise InterruptedError("run_stop_requested")
                    output_stream.write(chunk)
                output_stream.flush()
                os.fsync(output_stream.fileno())
        if ctx.should_stop():
            raise InterruptedError("run_stop_requested")
        if overwrite:
            os.replace(temporary_path, target)
        else:
            os.link(temporary_path, target)

        if mode == 1:
            try:
                source.unlink()
            except OSError as exc:
                return _operational_failure(
                    f"Destination was published, but the source was retained because deletion failed: {exc}"
                )
        return NodeResult(outputs={"successful": True})
    except InterruptedError:
        raise
    except OSError as exc:
        return _operational_failure(f"File operation failed: {exc}")
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _is_safe_directory(path: Path) -> bool:
    status = path.lstat()
    return stat.S_ISDIR(status.st_mode) and not bool(
        getattr(status, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def execute_delete_file(ctx: ExecutionContext) -> NodeResult:
    file_path = _required_resolved_path(ctx, "file_path", "File path")
    try:
        if not _is_regular_unlinked_file(file_path):
            return _operational_failure(f"File path is not a regular file: {file_path}")
        if ctx.should_stop():
            raise InterruptedError("run_stop_requested")
        file_path.unlink()
        return NodeResult(outputs={"successful": True})
    except InterruptedError:
        raise
    except OSError as exc:
        return _operational_failure(f"Delete file failed: {exc}")


__all__ = [
    "execute_combine_file_paths",
    "execute_construct_file_path",
    "execute_contents_in_directory",
    "execute_create_directory",
    "execute_deconstruct_file_path",
    "execute_delete_file",
    "execute_move_file",
    "execute_temporary_file_path",
]
