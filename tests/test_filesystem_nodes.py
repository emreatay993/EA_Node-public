# Purpose: Verify built-in filesystem node runtime behavior.
# Map: feature_routes/core_integrations_file_process_email_spreadsheet.md
# Tests: tests/test_filesystem_nodes.py

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from ea_node_editor.nodes.builtins import filesystem
from ea_node_editor.nodes.builtins.filesystem import (
    execute_combine_file_paths,
    execute_contents_in_directory,
    execute_construct_file_path,
    execute_create_directory,
    execute_deconstruct_file_path,
    execute_delete_file,
    execute_move_file,
    execute_temporary_file_path,
)
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeInputNotReadyError
from ea_node_editor.runtime_contracts import RuntimeArtifactRef


def _context(*, inputs: dict | None = None, properties: dict | None = None) -> ExecutionContext:
    return ExecutionContext(
        run_id="run",
        node_id="node",
        workspace_id="workspace",
        inputs=inputs or {},
        properties=properties or {},
        emit_log=lambda _level, _message: None,
        path_resolver=lambda value: Path(value).absolute(),
    )


def _artifact() -> RuntimeArtifactRef:
    return RuntimeArtifactRef.staged(
        "artifact",
        data_type_id="core.path",
        schema_version=1,
        format="txt",
        size_bytes=0,
        sha256="0" * 64,
        provenance="test",
    )


def test_combine_uses_host_join_semantics_and_preserves_unicode_and_empty_segments() -> None:
    cases = [
        (["relative", "", "döküman.txt"], os.path.join("relative", "", "döküman.txt")),
        (["base", os.path.sep + "rooted", "file.txt"], os.path.join("base", os.path.sep + "rooted", "file.txt")),
    ]
    if os.name == "nt":
        cases.extend(
            [
                ([r"C:\base", r"D:\rooted", "file.txt"], os.path.join(r"C:\base", r"D:\rooted", "file.txt")),
                ([r"\\server\share", "folder", "file.txt"], os.path.join(r"\\server\share", "folder", "file.txt")),
            ]
        )
    for paths, expected in cases:
        result = execute_combine_file_paths(_context(inputs={"paths": paths}))
        assert result.outputs == {"final_path": expected}


def test_construct_normalizes_extension_and_connected_values_override_properties() -> None:
    ctx = _context(
        inputs={"directory": Path("connected"), "file_name": "café", "file_extension": ""},
        properties={"directory": "configured", "file_name": "ignored", "file_extension": "txt"},
    )
    assert execute_construct_file_path(ctx).outputs == {
        "file_path": os.path.join("connected", "café")
    }
    ctx.inputs["file_extension"] = "tar.gz"
    assert execute_construct_file_path(ctx).outputs["file_path"].endswith("café.tar.gz")
    ctx.inputs["file_extension"] = ".txt"
    assert execute_construct_file_path(ctx).outputs["file_path"].endswith("café.txt")


def test_deconstruct_uses_final_extension_and_handles_root_and_unc_paths() -> None:
    paths = [
        os.path.join(os.path.sep, "tmp", "archive.tar.gz"),
        "café",
    ]
    if os.name == "nt":
        paths.extend([r"C:\folder\archive.tar.gz", r"\\server\share\folder\file.txt"])
    for path in paths:
        directory, component = os.path.split(path)
        file_name, extension = os.path.splitext(component)
        assert execute_deconstruct_file_path(_context(inputs={"file_path": path})).outputs == {
            "directory": directory,
            "file_name": file_name,
            "file_extension": extension,
        }


@pytest.mark.parametrize("executor,inputs", [
    (execute_combine_file_paths, {}),
    (execute_construct_file_path, {}),
    (execute_construct_file_path, {"directory": "base"}),
    (execute_construct_file_path, {"directory": "base", "file_name": "name"}),
    (execute_deconstruct_file_path, {}),
])
def test_missing_required_inputs_wait(executor, inputs: dict) -> None:
    with pytest.raises(NodeInputNotReadyError):
        executor(_context(inputs=inputs))


@pytest.mark.parametrize("value", [_artifact(), "saved://artifact", "temp://artifact"])
def test_lexical_nodes_reject_artifact_references(value: object) -> None:
    with pytest.raises(TypeError, match="artifact references"):
        execute_combine_file_paths(_context(inputs={"paths": [value]}))


@pytest.mark.parametrize(
    "inputs",
    [
        {"paths": "one/path"},
        {"paths": []},
        {"paths": [1]},
    ],
)
def test_combine_rejects_malformed_lists(inputs: dict) -> None:
    with pytest.raises((TypeError, ValueError)):
        execute_combine_file_paths(_context(inputs=inputs))


@pytest.mark.parametrize(
    "key,value",
    [("file_name", ""), ("file_name", os.path.join("nested", "name")), ("file_extension", "nested/ext")],
)
def test_construct_rejects_invalid_components(key: str, value: str) -> None:
    inputs = {"directory": "base", "file_name": "name", "file_extension": "txt"}
    inputs[key] = value
    with pytest.raises((NodeInputNotReadyError, ValueError)):
        execute_construct_file_path(_context(inputs=inputs))


@pytest.mark.skipif(os.name != "nt", reason="Windows filename rules")
@pytest.mark.parametrize(
    "file_name,file_extension",
    [
        ("bad:name", "txt"),
        ("wild*card", "txt"),
        ("control\x1f", "txt"),
        ("trailing ", "txt"),
        ("CON", ""),
        ("con", "txt"),
        ("LPT9", ".log"),
        ("COM¹", "txt"),
        ("LPT²", "txt"),
        ("CONIN$", "txt"),
        ("CONOUT$", "txt"),
        ("CON ", "log"),
    ],
)
def test_construct_rejects_windows_invalid_and_reserved_file_names(
    file_name: str,
    file_extension: str,
) -> None:
    with pytest.raises(ValueError):
        execute_construct_file_path(
            _context(
                inputs={
                    "directory": r"C:\output",
                    "file_name": file_name,
                    "file_extension": file_extension,
                }
            )
        )


def test_contents_filters_literal_patterns_modes_depth_and_sorts(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "a[1].txt").write_text("a", encoding="utf-8")
    (tmp_path / "nested" / "c.txt").write_text("c", encoding="utf-8")
    result = execute_contents_in_directory(
        _context(inputs={
            "directory": tmp_path,
            "search_pattern": "*[1].txt",
            "subdirectory_levels": 1,
            "content_type": 0,
        })
    )
    assert result.outputs == {"content_paths": [str((tmp_path / "a[1].txt").absolute())]}

    nested_result = execute_contents_in_directory(
        _context(inputs={"directory": tmp_path, "search_pattern": "?.txt", "subdirectory_levels": 1})
    )
    assert nested_result.outputs["content_paths"] == sorted(
        [
            str((tmp_path / "b.txt").absolute()),
            str((tmp_path / "nested" / "c.txt").absolute()),
        ],
        key=os.path.normcase,
    )

    result = execute_contents_in_directory(
        _context(inputs={
            "directory": tmp_path,
            "search_pattern": "*",
            "subdirectory_levels": 0,
            "content_type": 2,
        })
    )
    assert result.outputs["content_paths"] == sorted(
        [str(path.absolute()) for path in tmp_path.iterdir()], key=os.path.normcase
    )


def test_contents_uses_project_parent_or_cwd_when_directory_is_omitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    expected = project_dir / "saved.txt"
    expected.write_text("x", encoding="utf-8")
    ctx = _context()
    ctx.project_path = str(project_dir / "sample.cxproj")
    assert execute_contents_in_directory(ctx).outputs == {"content_paths": [str(expected)]}

    monkeypatch.chdir(tmp_path)
    cwd_file = tmp_path / "cwd.txt"
    cwd_file.write_text("x", encoding="utf-8")
    assert str(cwd_file.absolute()) in execute_contents_in_directory(_context()).outputs["content_paths"]


@pytest.mark.parametrize("key,value", [
    ("subdirectory_levels", True),
    ("subdirectory_levels", 11),
    ("content_type", False),
    ("content_type", 3),
])
def test_contents_rejects_invalid_integer_settings(tmp_path: Path, key: str, value: object) -> None:
    inputs = {"directory": tmp_path, key: value}
    with pytest.raises((TypeError, ValueError)):
        execute_contents_in_directory(_context(inputs=inputs))


def test_contents_honors_cancellation(tmp_path: Path) -> None:
    ctx = _context(inputs={"directory": tmp_path})
    ctx.should_stop = lambda: True
    with pytest.raises(InterruptedError, match="run_stop_requested"):
        execute_contents_in_directory(ctx)


def test_contents_does_not_recurse_through_directory_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "hidden.txt").write_text("x", encoding="utf-8")
    link = root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symlinks are unavailable")
    result = execute_contents_in_directory(
        _context(inputs={"directory": root, "subdirectory_levels": 1, "content_type": 2})
    )
    assert result.outputs == {"content_paths": [str(link.absolute())]}


def test_contents_does_not_recurse_through_controlled_reparse_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    linklike = tmp_path / "linklike"
    linklike.mkdir()
    (linklike / "hidden.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        filesystem,
        "_entry_is_reparse_point",
        lambda entry: entry.name == "linklike",
    )
    result = execute_contents_in_directory(
        _context(inputs={"directory": tmp_path, "subdirectory_levels": 1})
    )
    assert result.outputs == {"content_paths": []}


def test_contents_propagates_reparse_inspection_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    child = tmp_path / "child"
    child.mkdir()

    def fail_inspection(_entry: os.DirEntry) -> bool:
        raise PermissionError("inspection denied")

    monkeypatch.setattr(filesystem, "_entry_is_reparse_point", fail_inspection)
    with pytest.raises(PermissionError, match="inspection denied"):
        execute_contents_in_directory(
            _context(inputs={"directory": tmp_path, "subdirectory_levels": 1})
        )


def test_create_directory_is_idempotent_and_recursive_only_when_requested(tmp_path: Path) -> None:
    target = tmp_path / "parent" / "child"
    with pytest.raises(FileNotFoundError):
        execute_create_directory(_context(inputs={"directory": target}))
    result = execute_create_directory(
        _context(
            inputs={"directory": target, "create_recursive": True},
            properties={"directory": tmp_path / "ignored", "create_recursive": False},
        )
    )
    assert result.outputs == {"created_directory": str(target.absolute())}
    assert execute_create_directory(_context(inputs={"directory": target})).outputs == result.outputs


def test_create_directory_requires_input_and_boolean_flag(tmp_path: Path) -> None:
    with pytest.raises(NodeInputNotReadyError):
        execute_create_directory(_context())
    with pytest.raises(TypeError, match="Boolean"):
        execute_create_directory(
            _context(inputs={"directory": tmp_path / "new", "create_recursive": 1})
        )


def test_create_directory_honors_cancellation_before_mutation(tmp_path: Path) -> None:
    target = tmp_path / "new"
    ctx = _context(inputs={"directory": target})
    ctx.should_stop = lambda: True
    with pytest.raises(InterruptedError, match="run_stop_requested"):
        execute_create_directory(ctx)
    assert not target.exists()


def test_temporary_file_path_is_stable_when_supplied_and_never_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(filesystem.tempfile, "gettempdir", lambda: str(tmp_path))
    inputs = {"file_name": "corex", "file_extension": "tmp"}
    first = Path(execute_temporary_file_path(_context(inputs=inputs)).outputs["file_path"])
    second = Path(execute_temporary_file_path(_context(inputs=inputs)).outputs["file_path"])
    assert first == second == Path(tempfile.gettempdir(), "corex.tmp").absolute()
    assert not first.exists()


def test_temporary_file_path_randomizes_each_missing_component(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(filesystem.tempfile, "gettempdir", lambda: str(tmp_path))
    first = Path(execute_temporary_file_path(_context()).outputs["file_path"])
    second = Path(execute_temporary_file_path(_context()).outputs["file_path"])
    assert first.parent == second.parent == Path(tempfile.gettempdir()).absolute()
    assert first.name != second.name
    assert first.suffix and second.suffix
    assert not first.exists() and not second.exists()


@pytest.mark.parametrize("value", [" saved://artifact ", "'temp://artifact'", '"saved://artifact"'])
def test_operational_nodes_reject_disguised_artifact_references(value: str) -> None:
    with pytest.raises(TypeError, match="artifact references"):
        execute_create_directory(_context(inputs={"directory": value}))


def test_move_file_copies_or_moves_to_file_and_directory_targets(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("payload", encoding="utf-8")
    copied = tmp_path / "copied.txt"
    assert execute_move_file(_context(inputs={"source_path": source, "target_path": copied})).outputs == {"successful": True}
    assert source.read_text(encoding="utf-8") == copied.read_text(encoding="utf-8") == "payload"

    destination = tmp_path / "destination"
    destination.mkdir()
    result = execute_move_file(_context(inputs={"source_path": source, "target_path": destination, "operation_mode": 1}))
    assert result.outputs == {"successful": True}
    assert not source.exists()
    assert (destination / source.name).read_text(encoding="utf-8") == "payload"


def test_move_file_overwrite_and_no_clobber(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    target = tmp_path / "target.txt"
    source.write_text("new", encoding="utf-8")
    target.write_text("old", encoding="utf-8")
    failed = execute_move_file(_context(inputs={"source_path": source, "target_path": target}))
    assert failed.outputs == {"successful": False}
    assert failed.warnings and target.read_text(encoding="utf-8") == "old"
    assert source.exists()
    succeeded = execute_move_file(_context(inputs={"source_path": source, "target_path": target, "overwrite_target_file": True}))
    assert succeeded.outputs == {"successful": True}
    assert target.read_text(encoding="utf-8") == "new"


def test_move_file_rejects_missing_directory_and_same_file_aliases(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("data", encoding="utf-8")
    for target in (source, tmp_path / "missing" / "target.txt"):
        result = execute_move_file(_context(inputs={"source_path": source, "target_path": target, "overwrite_target_file": True}))
        assert result.outputs == {"successful": False}
    alias = tmp_path / "alias.txt"
    try:
        os.link(source, alias)
    except OSError:
        pytest.skip("Hard links are unavailable")
    result = execute_move_file(_context(inputs={"source_path": source, "target_path": alias, "overwrite_target_file": True}))
    assert result.outputs == {"successful": False}
    assert source.read_text(encoding="utf-8") == alias.read_text(encoding="utf-8") == "data"


def test_move_file_rejects_directories_missing_sources_and_bad_configuration(tmp_path: Path) -> None:
    directory = tmp_path / "directory"
    directory.mkdir()
    for source in (directory, tmp_path / "missing.txt"):
        result = execute_move_file(_context(inputs={"source_path": source, "target_path": tmp_path / "out.txt"}))
        assert result.outputs == {"successful": False}
        assert result.warnings
    with pytest.raises(NodeInputNotReadyError):
        execute_move_file(_context())
    with pytest.raises(TypeError):
        execute_move_file(_context(inputs={"source_path": _artifact(), "target_path": tmp_path / "out"}))
    with pytest.raises((TypeError, ValueError)):
        execute_move_file(_context(inputs={"source_path": "x", "target_path": "y", "operation_mode": 2}))
    with pytest.raises(TypeError, match="Boolean"):
        execute_move_file(_context(inputs={"source_path": "x", "target_path": "y", "overwrite_target_file": 1}))


def test_move_file_publication_failure_preserves_source_and_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.txt"
    target = tmp_path / "target.txt"
    source.write_text("new", encoding="utf-8")
    monkeypatch.setattr(filesystem.os, "link", lambda *_args: (_ for _ in ()).throw(PermissionError("publish denied")))
    result = execute_move_file(_context(inputs={"source_path": source, "target_path": target, "operation_mode": 1}))
    assert result.outputs == {"successful": False}
    assert source.read_text(encoding="utf-8") == "new" and not target.exists()
    assert not list(tmp_path.glob(".*.corex-tmp-*"))


def test_move_file_source_open_failure_closes_staging_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.txt"
    target = tmp_path / "target.txt"
    source.write_text("data", encoding="utf-8")
    descriptor = -1
    real_mkstemp = tempfile.mkstemp

    def tracked_mkstemp(*args, **kwargs):
        nonlocal descriptor
        descriptor, temporary = real_mkstemp(*args, **kwargs)
        return descriptor, temporary

    original_open = Path.open

    def fail_source_open(path: Path, *args, **kwargs):
        if path == source:
            raise PermissionError("source denied")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(filesystem.tempfile, "mkstemp", tracked_mkstemp)
    monkeypatch.setattr(Path, "open", fail_source_open)
    result = execute_move_file(_context(inputs={"source_path": source, "target_path": target}))
    assert result.outputs == {"successful": False}
    with pytest.raises(OSError):
        os.fstat(descriptor)
    assert source.exists() and not target.exists()
    assert not list(tmp_path.glob(".*.corex-tmp-*"))


def test_move_file_staging_cleanup_failure_does_not_abort_published_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.txt"
    target = tmp_path / "target.txt"
    source.write_text("data", encoding="utf-8")
    original_unlink = Path.unlink

    def fail_staging_unlink(path: Path, *args, **kwargs) -> None:
        if ".corex-tmp-" in path.name:
            raise PermissionError("cleanup denied")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_staging_unlink)
    result = execute_move_file(
        _context(inputs={"source_path": source, "target_path": target, "operation_mode": 1})
    )
    assert result.outputs == {"successful": True}
    assert not source.exists() and target.read_text(encoding="utf-8") == "data"
    staging = list(tmp_path.glob(".*.corex-tmp-*"))
    assert len(staging) == 1
    os.unlink(staging[0])


def test_move_file_cancellation_before_and_during_copy_cleans_staging(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"x" * (2 * 1024 * 1024))
    for stop in (lambda: True, iter((False, False, True)).__next__):
        target = tmp_path / f"target-{target_name(stop)}.bin"
        ctx = _context(inputs={"source_path": source, "target_path": target})
        ctx.should_stop = stop
        with pytest.raises(InterruptedError, match="run_stop_requested"):
            execute_move_file(ctx)
        assert not target.exists() and source.exists()
        assert not list(tmp_path.glob(".*.corex-tmp-*"))


def target_name(value: object) -> str:
    return str(id(value))


def test_move_file_source_unlink_failure_reports_published_destination(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.txt"
    target = tmp_path / "target.txt"
    source.write_text("data", encoding="utf-8")
    original_unlink = Path.unlink
    def fail_source_unlink(path: Path, *args, **kwargs) -> None:
        if path == source:
            raise PermissionError("unlink denied")
        original_unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", fail_source_unlink)
    result = execute_move_file(_context(inputs={"source_path": source, "target_path": target, "operation_mode": 1}))
    assert result.outputs == {"successful": False}
    assert "published" in result.warnings[0] and "retained" in result.warnings[0]
    assert source.exists() and target.read_text(encoding="utf-8") == "data"


def test_delete_file_success_failures_and_cancellation(tmp_path: Path) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("data", encoding="utf-8")
    ctx = _context(inputs={"file_path": file_path})
    ctx.should_stop = lambda: True
    with pytest.raises(InterruptedError, match="run_stop_requested"):
        execute_delete_file(ctx)
    assert file_path.exists()
    assert execute_delete_file(_context(inputs={"file_path": file_path})).outputs == {"successful": True}
    for path in (file_path, tmp_path):
        result = execute_delete_file(_context(inputs={"file_path": path}))
        assert result.outputs == {"successful": False} and result.warnings
    with pytest.raises(NodeInputNotReadyError):
        execute_delete_file(_context())
