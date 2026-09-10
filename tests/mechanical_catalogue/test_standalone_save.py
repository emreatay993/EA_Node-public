# Purpose: Verify standalone Mechanical save declaration, native staging, publication, and runtime freshness.
# Map: subsystems/addons.md
# Tests: this file

from __future__ import annotations

import json
import os
import sys
import types
import zipfile
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from uuid import uuid4

import pytest

from ea_node_editor.addons.mechanical.backend import MechanicalOwnerBackend
from ea_node_editor.addons.mechanical.catalog import MECHANICAL_ADDON_ID
from ea_node_editor.addons.mechanical.contracts import catalogue_table, model_handle
from ea_node_editor.addons.mechanical.function_nodes import SOURCE
from ea_node_editor.addons.mechanical.property_edit import MechanicalPropertyEditAdapter
from ea_node_editor.addons.mechanical.runtime import execute_save_model
from ea_node_editor.addons.mechanical.saving import (
    SaveStaging,
    companion_path,
    create_save_staging,
    preflight_save_destination,
    publish_save,
    resolve_save_format,
    validate_archive_inclusions,
)
from ea_node_editor.addons.mechanical.session import StaleMechanicalModelError
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeInputNotReadyError
from ea_node_editor.addons.property_edit_adapters import PropertyEditAdapterContext
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.runtime_contracts import TableValue
from tests.mechanical_catalogue.test_contracts import _model_metadata, _row


SAVE_DATA_TYPES = build_default_registry(
    include_public_plugins=False,
    addon_runtime_config=(("mechanical.corex", True),),
).data_types


def test_registered_save_node_has_every_typed_exposed_control() -> None:
    declaration = next(
        item
        for item in discover_plugin_declarations(
            SOURCE,
            filename="mechanical_nodes.py",
            allow_reserved_ids=True,
            owner_id=MECHANICAL_ADDON_ID,
            allow_internal_metadata=True,
        )
        if item.spec.type_id == "mechanical.save_model"
    )
    assert declaration.spec.solution_reuse_scope == "never"
    assert [
        (port.key, port.data_type, port.data_access)
        for port in declaration.spec.ports
    ] == [
        ("source_model", "COREX.Mechanical.Model", "item"),
        ("file", "COREX.DataTypes.Path", "item"),
        ("format", "COREX.DataTypes.String", "item"),
        ("include_results", "COREX.DataTypes.Bool", "item"),
        ("include_user_files", "COREX.DataTypes.Bool", "item"),
        ("include_external_imported_files", "COREX.DataTypes.Bool", "item"),
        ("overwrite", "COREX.DataTypes.Bool", "item"),
        ("model", "COREX.Mechanical.Model", "item"),
        ("files", "COREX.DataTypes.Path", "list"),
        ("report", "COREX.DataTypes.TableValue", "item"),
    ]
    assert next(
        prop for prop in declaration.spec.properties if prop.key == "format"
    ).enum_values == (
        "auto", "mechdb", "mechdat", "mechpz", "wbpj", "wbpz"
    )
    ports = {port.key: port for port in declaration.spec.ports}
    assert ports["source_model"].required is True
    assert ports["file"].required is True
    assert all(port.exposed for port in declaration.spec.ports)


def test_archive_controls_remain_present_but_inactive_when_unconsumed() -> None:
    adapter = MechanicalPropertyEditAdapter()
    items = [
        {"key": key, "editor_enabled": True, "condition_enabled": True}
        for key in (
            "include_results", "include_user_files", "include_external_imported_files"
        )
    ]
    context = PropertyEditAdapterContext(
        node=SimpleNamespace(
            type_id="mechanical.save_model",
            properties={"format": "mechdb", "file": "saved.mechdb"},
        )
    )
    projected = adapter.build_property_items(context, items)
    assert all(item["editor_enabled"] is False for item in projected)
    context.node.properties.update(format="mechpz", file="saved.mechpz")
    projected = adapter.build_property_items(context, items)
    assert [item["editor_enabled"] for item in projected] == [True, True, False]


@pytest.mark.parametrize("suffix", ["mechdb", "mechdat", "mechpz"])
def test_format_auto_and_explicit_extension_agreement(tmp_path: Path, suffix: str) -> None:
    destination = tmp_path / f"saved.{suffix}"
    assert resolve_save_format(destination, "auto") == suffix
    assert resolve_save_format(destination, suffix) == suffix
    other = "mechdb" if suffix != "mechdb" else "mechdat"
    with pytest.raises(ValueError, match="does not agree"):
        resolve_save_format(destination, other)


def test_preflight_requires_explicit_source_overwrite_and_checks_companion(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    companion = companion_path(source, "mechdb")
    assert companion is not None
    companion.mkdir()
    (companion / "data.rst").write_bytes(b"result")
    with pytest.raises(FileExistsError, match="source overwrite requires"):
        preflight_save_destination(
            source, source=source, format_code="mechdb", overwrite=False
        )
    checked = []
    monkeypatch.setattr(
        "ea_node_editor.addons.mechanical.saving._assert_bundle_unlocked",
        lambda path: checked.append(path),
    )
    preflight = preflight_save_destination(
        source, source=source, format_code="mechdb", overwrite=True
    )
    assert (preflight.destination, preflight.companion, preflight.source_destination) == (
        source, companion, True,
    )
    assert source in checked and companion in checked


def test_preflight_rejects_source_alias_and_locked_destination(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    alias = tmp_path / "alias.mechdb"
    os.link(source, alias)
    with pytest.raises(ValueError, match="aliases the source"):
            preflight_save_destination(
            alias, source=source, format_code="mechdb", overwrite=True
        )
    destination = tmp_path / "destination.mechdb"
    destination.write_bytes(b"existing")
    monkeypatch.setattr(
        "ea_node_editor.addons.mechanical.saving._assert_bundle_unlocked",
        lambda path: (_ for _ in ()).throw(PermissionError(f"locked: {path}")),
    )
    with pytest.raises(PermissionError, match="locked"):
        preflight_save_destination(
            destination, source=source, format_code="mechdb", overwrite=True
        )


def _stage_bundle(tmp_path: Path, *, content: bytes = b"new") -> SaveStaging:
    destination = tmp_path / "saved.mechdb"
    staging = create_save_staging(destination, "mechdb")
    staging.primary.write_bytes(content)
    assert staging.companion is not None
    staging.companion.mkdir()
    (staging.companion / "model.dat").write_bytes(content + b"-companion")
    return staging


def test_publication_moves_complete_native_bundle(tmp_path: Path) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    staging = _stage_bundle(tmp_path)
    destination = tmp_path / "saved.mechdb"
    preflight = preflight_save_destination(
        destination, source=source, format_code="mechdb", overwrite=False
    )
    publication = publish_save(
        staging,
        preflight=preflight,
        format_code="mechdb",
    )
    assert publication.files == [destination, companion_path(destination, "mechdb")]
    assert destination.read_bytes() == b"new"
    assert (publication.files[1] / "model.dat").read_bytes() == b"new-companion"
    assert staging.root.exists()
    publication.commit()
    assert not staging.root.exists()


def test_existing_bundle_survives_publication_failure(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    destination = tmp_path / "saved.mechdb"
    destination.write_bytes(b"old")
    old_companion = companion_path(destination, "mechdb")
    assert old_companion is not None
    old_companion.mkdir()
    (old_companion / "old.dat").write_bytes(b"old-companion")
    staging = _stage_bundle(tmp_path)
    preflight = preflight_save_destination(
        destination, source=source, format_code="mechdb", overwrite=True
    )
    monkeypatch.setattr(os, "link", lambda *_args: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        publish_save(
            staging,
            preflight=preflight,
            format_code="mechdb",
        )
    assert destination.read_bytes() == b"old"
    assert (old_companion / "old.dat").read_bytes() == b"old-companion"
    assert not staging.root.exists()


def test_external_replacement_keeps_exact_recovery_bundle(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    destination = tmp_path / "saved.mechdb"
    destination.write_bytes(b"old")
    old_companion = companion_path(destination, "mechdb")
    assert old_companion is not None
    old_companion.mkdir()
    (old_companion / "old.dat").write_bytes(b"old-companion")
    staging = _stage_bundle(tmp_path)
    preflight = preflight_save_destination(
        destination, source=source, format_code="mechdb", overwrite=True
    )

    def fail_after_replacement(*_args):
        (old_companion / "external.dat").write_bytes(b"external")
        raise OSError("injected publish failure")

    monkeypatch.setattr(os, "link", fail_after_replacement)
    with pytest.raises(RuntimeError, match="publication_recovery_required") as raised:
        publish_save(
            staging,
            preflight=preflight,
            format_code="mechdb",
        )
    assert (old_companion / "external.dat").read_bytes() == b"external"
    recovery = Path(str(raised.value).split(": ", 1)[1].split(";", 1)[0])
    assert recovery == staging.root and recovery.is_dir()
    assert any((recovery / "backups").iterdir())


def test_existing_single_file_uses_atomic_replace_and_rolls_back_until_commit(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    destination = tmp_path / "saved.mechpz"
    _archive(destination, {"old.mechdb": b"old"})
    old = destination.read_bytes()
    preflight = preflight_save_destination(
        destination, source=source, format_code="mechpz", overwrite=True
    )
    staging = create_save_staging(destination, "mechpz")
    _archive(staging.primary, {"new.mechdb": b"new"})
    real_replace = os.replace
    replacements = []

    def record_replace(source_path, destination_path):
        replacements.append((Path(source_path), Path(destination_path)))
        return real_replace(source_path, destination_path)

    monkeypatch.setattr(os, "replace", record_replace)
    publication = publish_save(
        staging, preflight=preflight, format_code="mechpz"
    )
    assert (staging.primary, destination) in replacements
    assert publication.backups[destination].is_file()
    publication.rollback()
    assert destination.read_bytes() == old
    assert not staging.root.exists()


def _archive(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as stream:
        for name, content in members.items():
            stream.writestr(name, content)


@pytest.mark.parametrize(
    ("include_results", "include_user", "members", "complete", "exclusions"),
    [
        (True, True, {"root_Mech_Files/Modal/file.rst": b"r", "root_Mech_Files/UserFiles/marker.txt": b"u"}, True, []),
        (False, True, {"root_Mech_Files/UserFiles/marker.txt": b"u"}, False, ["result/solution files"]),
        (True, False, {"root_Mech_Files/Modal/file.rst": b"r"}, False, ["user files"]),
    ],
)
def test_archive_inclusion_and_each_exclusion(
    tmp_path: Path,
    include_results: bool,
    include_user: bool,
    members: dict[str, bytes],
    complete: bool,
    exclusions: list[str],
) -> None:
    work = tmp_path / "work.mechdb"
    work.write_bytes(b"work")
    work_files = companion_path(work, "mechdb")
    assert work_files is not None
    (work_files / "Modal").mkdir(parents=True)
    (work_files / "UserFiles").mkdir()
    (work_files / "Modal" / "file.rst").write_bytes(b"r")
    (work_files / "UserFiles" / "marker.txt").write_bytes(b"u")
    archive = tmp_path / "saved.mechpz"
    _archive(archive, members)
    result = validate_archive_inclusions(
        archive,
        work_path=work,
        result_directories=[str(work_files / "Modal")],
        user_directory=str(work_files / "UserFiles"),
        include_results=include_results,
        include_user_files=include_user,
    )
    assert result["complete"] is complete
    assert result["exclusions"] == exclusions
    assert result["external_imported_files_consumed"] is False


def test_archive_missing_requested_file_fails(tmp_path: Path) -> None:
    work = tmp_path / "work.mechdb"
    work.write_bytes(b"work")
    work_files = companion_path(work, "mechdb")
    assert work_files is not None
    (work_files / "Modal").mkdir(parents=True)
    (work_files / "Modal" / "file.rst").write_bytes(b"result")
    archive = tmp_path / "missing.mechpz"
    _archive(archive, {"work.mechdb": b"work"})
    with pytest.raises(RuntimeError, match="requested result/solution inventory differs"):
        validate_archive_inclusions(
            archive,
            work_path=work,
            result_directories=[str(work_files / "Modal")],
            user_directory="",
            include_results=True,
            include_user_files=True,
        )


def test_archive_rejects_truncated_same_name_and_accepts_empty_native_inventory(
    tmp_path: Path,
) -> None:
    work = tmp_path / "work.mechdb"
    work.write_bytes(b"work")
    work_files = companion_path(work, "mechdb")
    assert work_files is not None
    result_root = work_files / "Modal"
    user_root = work_files / "UserFiles"
    result_root.mkdir(parents=True)
    user_root.mkdir()
    (result_root / "solve.out").write_bytes(b"complete output")
    archive = tmp_path / "truncated.mechpz"
    _archive(archive, {"work_Mech_Files/Modal/solve.out": b"short"})
    with pytest.raises(RuntimeError, match="changed Modal/solve.out"):
        validate_archive_inclusions(
            archive,
            work_path=work,
            result_directories=[str(result_root)],
            user_directory=str(user_root),
            include_results=True,
            include_user_files=True,
        )
    (result_root / "solve.out").unlink()
    empty = tmp_path / "empty.mechpz"
    _archive(empty, {"work.mechdb": b"work"})
    proof = validate_archive_inclusions(
        empty,
        work_path=work,
        result_directories=[str(result_root)],
        user_directory=str(user_root),
        include_results=True,
        include_user_files=True,
    )
    assert proof["result_roots_checked"] == 1
    assert proof["result_files_checked"] == 0
    assert proof["user_files_checked"] == 0


class _Sessions:
    def __init__(self, tmp_path: Path, source: Path, *, fail_publish=False):
        work = tmp_path / "working.mechdb"
        work.write_bytes(b"working")
        work_files = companion_path(work, "mechdb")
        assert work_files is not None
        work_files.mkdir()
        (work_files / "UserFiles").mkdir()
        self.session = SimpleNamespace(
            revision=2,
            work_root=tmp_path,
            work_path=work,
            source_path=source,
            terminal=False,
        )
        self.calls = []
        self.registered = []
        self.retired = False
        self.fail_publish = fail_publish

    def admit_model(self, model, **_kwargs):
        if model.metadata["model_revision"] != self.session.revision:
            raise StaleMechanicalModelError("stale")
        return self.session

    def operate(self, _session, **kwargs):
        self.calls.append(kwargs)
        self.session.revision += 1
        args = kwargs["args"]
        stage = Path(args["stage_path"])
        if args["format"] == "mechpz":
            _archive(stage, {"working.mechdb": b"native"})
        else:
            stage.write_bytes(b"native")
            stage_files = Path(args["stage_companion"])
            stage_files.mkdir()
            (stage_files / "model.dat").write_bytes(b"companion")
        row = _row(
            model_revision=3,
            catalogue_id=args["catalogue_identity"]["catalogue_id"],
            producer_node_id="save-1",
            producer_port="report",
            producer_path="[3,1]",
            producer_iteration=4,
        )
        return {
            "status": "staged",
            "native_save": {
                "schema_version": 1,
                "format": args["format"],
                "reopen_verified": True,
                "work_restored": True,
                "object_count": 1,
                "stage_bytes": stage.stat().st_size,
                "analysis_states": [],
                "reopened_analysis_states": [],
                "result_directories": [],
                "user_directory": (
                    str(self.session.work_path.with_name(
                        self.session.work_path.stem + "_Mech_Files"
                    ) / "UserFiles")
                    if args["format"] == "mechpz"
                    else ""
                ),
                "user_directory_status": (
                    "available" if args["format"] == "mechpz" else "not_consumed"
                ),
            },
            "catalogue": catalogue_table([row]),
        }

    def register_model(self, _session, **kwargs):
        self.registered.append(kwargs)
        return kwargs

    def retire_session(self, _session):
        self.retired = True


def _context(tmp_path: Path, sessions: _Sessions, destination: Path, **properties):
    values = {
        "file": str(destination),
        "format": "auto",
        "include_results": True,
        "include_user_files": True,
        "include_external_imported_files": "must-not-be-read",
        "overwrite": False,
        **properties,
    }
    invalidations = []
    return ExecutionContext(
        run_id="run-1",
        node_id="save-1",
        workspace_id="workspace-1",
        inputs={},
        properties=values,
        emit_log=lambda *_: None,
        path_resolver=lambda value: Path(value),
        worker_services=SimpleNamespace(
            mechanical_session_service=sessions,
            data_types=SAVE_DATA_TYPES,
        ),
        target_path=(3, 1),
        target_iteration=4,
        workspace_node_types=MappingProxyType(
            {"open-1": "mechanical.open_model", "save-1": "mechanical.save_model"}
        ),
        _request_observation_invalidation=lambda root, reason: invalidations.append((root, reason)),
    ), invalidations


def _model(*, revision=2):
    return model_handle(
        handle_id="model",
        owner_scope="run-1",
        worker_generation=1,
        metadata=_model_metadata(model_revision=revision),
    )


@pytest.mark.parametrize("suffix", ["mechdb", "mechdat"])
def test_runtime_nonarchive_ignores_all_inclusion_controls_and_returns_fresh_outputs(
    tmp_path: Path, suffix: str
) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    destination = tmp_path / f"saved.{suffix}"
    sessions = _Sessions(tmp_path, source)
    ctx, invalidations = _context(
        tmp_path,
        sessions,
        destination,
        include_results="inactive",
        include_user_files="inactive",
    )
    result = execute_save_model(ctx, _model(), SimpleNamespace(**ctx.properties))
    args = sessions.calls[0]["args"]
    assert not {"include_results", "include_user_files", "include_external_imported_files"} & args.keys()
    assert sessions.calls[0]["mutation"] is True
    assert invalidations == [("open-1", "mechanical_model_mutated")]
    assert result["files"] == [
        str(destination), str(companion_path(destination, suffix))
    ]
    assert result["model"]["producer_node_id"] == "save-1"
    assert isinstance(result["report"], TableValue)
    assert source.read_bytes() == b"source"
    with pytest.raises(ValueError, match="stale_reference"):
        execute_save_model(ctx, _model(), SimpleNamespace(**ctx.properties))


def test_runtime_archive_consumes_two_controls_but_never_external(tmp_path: Path) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    destination = tmp_path / "saved.mechpz"
    sessions = _Sessions(tmp_path, source)
    ctx, _invalidations = _context(
        tmp_path,
        sessions,
        destination,
        include_results=False,
        include_user_files=True,
    )
    result = execute_save_model(ctx, _model(), SimpleNamespace(**ctx.properties))
    args = sessions.calls[0]["args"]
    assert args["include_results"] is False and args["include_user_files"] is True
    assert "include_external_imported_files" not in args
    assert result["files"] == [str(destination)]


def test_explicit_source_overwrite_publishes_only_when_enabled(tmp_path: Path) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    sessions = _Sessions(tmp_path, source)
    ctx, _invalidations = _context(tmp_path, sessions, source, overwrite=True)
    result = execute_save_model(ctx, _model(), SimpleNamespace(**ctx.properties))
    assert source.read_bytes() == b"native"
    assert result["files"] == [str(source), str(companion_path(source, "mechdb"))]


def test_source_change_after_preflight_blocks_publication_and_retains_recovery(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")

    class RacingSessions(_Sessions):
        def operate(self, session, **kwargs):
            result = super().operate(session, **kwargs)
            self.session.source_path.write_bytes(b"external")
            return result

    sessions = RacingSessions(tmp_path, source)
    ctx, _invalidations = _context(tmp_path, sessions, source, overwrite=True)
    with pytest.raises(RuntimeError, match="staged recovery retained at") as raised:
        execute_save_model(ctx, _model(), SimpleNamespace(**ctx.properties))
    assert source.read_bytes() == b"external"
    recovery = Path(str(raised.value).split("retained at ", 1)[1].split(";", 1)[0])
    assert recovery.is_dir()


def test_external_destination_create_during_native_staging_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    destination = tmp_path / "saved.mechdb"

    class RacingSessions(_Sessions):
        def operate(self, session, **kwargs):
            result = super().operate(session, **kwargs)
            destination.write_bytes(b"external")
            return result

    sessions = RacingSessions(tmp_path, source)
    ctx, _invalidations = _context(tmp_path, sessions, destination)
    with pytest.raises(RuntimeError, match="staged recovery retained at"):
        execute_save_model(ctx, _model(), SimpleNamespace(**ctx.properties))
    assert destination.read_bytes() == b"external"


def test_byte_identical_companion_replacement_after_preflight_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    destination = tmp_path / "saved.mechdb"
    destination.write_bytes(b"old")
    companion = companion_path(destination, "mechdb")
    assert companion is not None
    companion.mkdir()
    (companion / "data.dat").write_bytes(b"same")

    class RacingSessions(_Sessions):
        def operate(self, session, **kwargs):
            result = super().operate(session, **kwargs)
            displaced = tmp_path / "displaced"
            os.replace(companion, displaced)
            companion.mkdir()
            (companion / "data.dat").write_bytes(b"same")
            return result

    sessions = RacingSessions(tmp_path, source)
    ctx, _invalidations = _context(tmp_path, sessions, destination, overwrite=True)
    with pytest.raises(RuntimeError, match="staged recovery retained at"):
        execute_save_model(ctx, _model(), SimpleNamespace(**ctx.properties))
    assert (companion / "data.dat").read_bytes() == b"same"


def test_late_model_registration_failure_rolls_back_explicit_source_overwrite(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")

    class FailingRegistration(_Sessions):
        def register_model(self, _session, **_kwargs):
            raise RuntimeError("injected late model registration failure")

    sessions = FailingRegistration(tmp_path, source)
    ctx, _invalidations = _context(tmp_path, sessions, source, overwrite=True)
    with pytest.raises(RuntimeError, match="late model registration failure"):
        execute_save_model(ctx, _model(), SimpleNamespace(**ctx.properties))
    assert source.read_bytes() == b"source"
    assert companion_path(source, "mechdb") is not None
    assert not companion_path(source, "mechdb").exists()


def test_output_encoding_failure_rolls_back_explicit_source_overwrite(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    sessions = _Sessions(tmp_path, source)
    ctx, _invalidations = _context(tmp_path, sessions, source, overwrite=True)
    monkeypatch.setattr(
        "ea_node_editor.addons.mechanical.runtime.serialize_runtime_value",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TypeError("injected encoding")),
    )
    with pytest.raises(TypeError, match="injected encoding"):
        execute_save_model(ctx, _model(), SimpleNamespace(**ctx.properties))
    assert source.read_bytes() == b"source"
    assert not companion_path(source, "mechdb").exists()


def test_generated_native_save_uses_no_internal_database_copy_or_dsdb() -> None:
    from ea_node_editor.addons.mechanical.saving import STANDALONE_SAVE_BODY

    assert "SaveAs" in STANDALONE_SAVE_BODY
    assert "ArchiveSettings" in STANDALONE_SAVE_BODY
    assert "Unarchive" in STANDALONE_SAVE_BODY
    assert "dsdb" not in STANDALONE_SAVE_BODY.casefold()
    assert "copy" not in STANDALONE_SAVE_BODY.casefold()


def test_workbench_mechpz_is_rejected_before_any_native_or_staging_work(tmp_path: Path) -> None:
    source = tmp_path / "source.wbpj"
    source.write_bytes(b"source")
    sessions = _Sessions(tmp_path, source)
    destination = tmp_path / "saved.mechpz"
    ctx, invalidations = _context(tmp_path, sessions, destination)
    with pytest.raises(ValueError, match="never valid for a Workbench source"):
        execute_save_model(ctx, _model(), SimpleNamespace(**ctx.properties))
    assert sessions.calls == [] and invalidations == []


def test_file_is_required_before_any_native_save(tmp_path: Path) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    sessions = _Sessions(tmp_path, source)
    ctx, invalidations = _context(tmp_path, sessions, tmp_path / "unused.mechdb", file="")
    with pytest.raises(NodeInputNotReadyError):
        execute_save_model(ctx, _model(), SimpleNamespace(**ctx.properties))
    assert sessions.calls == [] and invalidations == []


class _NativeObject:
    ObjectId = 1
    Name = "Model"
    Parent = None
    VisibleProperties = []

    @staticmethod
    def GetType():
        return SimpleNamespace(FullName="Ansys.ACT.Automation.Mechanical.Model")


class _NativeProject:
    def __init__(self, work: Path):
        self.FilePath = str(work)
        self.UserFiles = str(work.with_name(work.stem + "_Mech_Files") / "UserFiles")
        self.calls = []

    def Save(self):
        self.calls.append(("Save", self.FilePath))

    def SaveAs(self, path, overwrite):
        target = Path(path)
        self.calls.append(("SaveAs", str(target), overwrite))
        target.write_bytes(b"native")
        companion = companion_path(target, target.suffix.casefold().removeprefix("."))
        assert companion is not None
        companion.mkdir()
        self.FilePath = str(target)

    def Open(self, path):
        self.calls.append(("Open", str(path)))
        self.FilePath = str(path)

    def Archive(self, *_args):
        raise AssertionError("nonarchive test must not archive")

    def Unarchive(self, *_args):
        raise AssertionError("nonarchive test must not unarchive")


class _NativeApp:
    def __init__(self, namespace):
        self.namespace = namespace

    def execute_script(self, script):
        exec(compile(script, "<mechanical-save-test>", "exec"), self.namespace)
        return self.namespace["_corex_receipt"]


def test_backend_uses_native_saveas_reopen_and_restores_working_model(tmp_path: Path) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    work = tmp_path / "work.mechdb"
    work.write_bytes(b"work")
    project = _NativeProject(work)
    tree = SimpleNamespace(AllObjects=[_NativeObject()])
    model = SimpleNamespace(Analyses=[SimpleNamespace(
        ObjectId=7,
        WorkingDir=None,
        ResultFileName="missing.rst",
        Solution=SimpleNamespace(Status="Done"),
        GetResultsData=lambda: None,
    )])
    data_model = SimpleNamespace(ObjectTags=[], Project=project)

    class Views:
        NumberOfViews = 0

        @staticmethod
        def ExportModelViews(path):
            Path(path).write_text("<ModelViewsManager />", encoding="utf-8")

    backend = MechanicalOwnerBackend()
    backend.app = _NativeApp({"DataModel": data_model, "Tree": tree, "Model": model})
    backend.tree = tree
    backend.model = model
    backend.data_model = data_model
    backend.graphics = SimpleNamespace(ModelViewManager=Views())
    backend.source_path = source.resolve()
    backend.work_path = work.resolve()
    backend.work_root = tmp_path.resolve()
    destination = tmp_path / "published.mechdb"
    staging = create_save_staging(destination, "mechdb")
    identity = _row(
        model_revision=3,
        catalogue_id=str(uuid4()),
        producer_node_id="save-1",
        producer_port="report",
        producer_path="[0]",
        producer_iteration=0,
        system_key="standalone",
    )
    identity = {key: identity[key] for key in (
        "schema_version", "model_revision", "producer_iteration", "catalogue_id",
        "producer_node_id", "producer_port", "producer_path", "run_id", "session_id",
        "document_id", "source_key", "system_key",
    )}
    result = backend.standalone_save({
        "format": "mechdb",
        "source_path": str(source),
        "destination_path": str(destination),
        "work_path": str(work),
        "stage_path": str(staging.primary),
        "stage_companion": str(staging.companion),
        "verify_path": str(staging.verify_project),
        "files": [str(destination), str(companion_path(destination, "mechdb"))],
        "overwrite": False,
        "catalogue_identity": identity,
        "view_export_path": str(tmp_path / "views.xml"),
    })
    assert result["status"] == "staged"
    assert result["native_save"]["reopen_verified"] is True
    assert result["native_save"]["analysis_states"][0]["solution_status"] == "Done"
    assert project.FilePath == str(work)
    assert [call[0] for call in project.calls] == ["Save", "SaveAs", "Open", "Open"]
    operation = next(row for row in result["rows"] if row["record_kind"] == "operation")
    assert json.loads(operation["message"])["publication"] == "complete"


class _ArchiveSettings:
    def __init__(self, include_results, include_user_files):
        self.IncludeResultAndSolutionFiles = include_results
        self.IncludeUserFiles = include_user_files


class _ArchiveProject(_NativeProject):
    def SaveAs(self, *_args):
        raise AssertionError("archive test must not SaveAs")

    def Archive(self, path, overwrite, settings):
        target = Path(path)
        self.calls.append(("Archive", str(target), overwrite, settings))
        members = {"work.mechdb": b"work"}
        if settings.IncludeResultAndSolutionFiles:
            members["work_Mech_Files/Modal/file.rst"] = b"result"
        if settings.IncludeUserFiles:
            members["work_Mech_Files/UserFiles/marker.txt"] = b"user"
        _archive(target, members)

    def Unarchive(self, archive, project, overwrite):
        self.calls.append(("Unarchive", str(archive), str(project), overwrite))
        Path(project).write_bytes(b"verified")
        self.FilePath = str(project)
        return str(project)


def test_backend_archive_maps_only_two_native_flags_and_reports_exclusion(
    tmp_path: Path, monkeypatch
) -> None:
    tmp_path = tmp_path / "native ³ ° Ω 漢字"
    tmp_path.mkdir()
    mechanical_module = types.ModuleType("Ansys.ACT.Automation.Mechanical")
    mechanical_module.ArchiveSettings = _ArchiveSettings
    for name in ("Ansys", "Ansys.ACT", "Ansys.ACT.Automation"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "Ansys.ACT.Automation.Mechanical", mechanical_module)
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    work = tmp_path / "work.mechdb"
    work.write_bytes(b"work")
    work_files = companion_path(work, "mechdb")
    assert work_files is not None
    (work_files / "Modal").mkdir(parents=True)
    (work_files / "UserFiles").mkdir()
    (work_files / "Modal" / "file.rst").write_bytes(b"result")
    (work_files / "UserFiles" / "marker.txt").write_bytes(b"user")
    project = _ArchiveProject(work)
    tree = SimpleNamespace(AllObjects=[_NativeObject()])
    data_model = SimpleNamespace(ObjectTags=[], Project=project)
    backend = MechanicalOwnerBackend()
    disposed_readers = []
    fail_dispose = [False]

    class Reader:
        def Dispose(self):
            disposed_readers.append(True)
            if fail_dispose[0]:
                raise RuntimeError("injected reader disposal error")

    analysis = SimpleNamespace(
        ObjectId=7,
        WorkingDir=str(work_files / "Modal"),
        ResultFileName=str(work_files / "Modal" / "file.rst"),
        Solution=SimpleNamespace(Status="Done"),
        GetResultsData=Reader,
    )
    native_model = SimpleNamespace(Analyses=[analysis])
    backend.app = _NativeApp({
        "DataModel": data_model,
        "Tree": tree,
        "Model": native_model,
    })
    backend.tree = tree
    backend.model = SimpleNamespace(Analyses=[])
    backend.data_model = data_model
    backend.graphics = SimpleNamespace(ModelViewManager=SimpleNamespace(NumberOfViews=0))
    backend.source_path = source.resolve()
    backend.work_path = work.resolve()
    backend.work_root = tmp_path.resolve()
    destination = tmp_path / "published.mechpz"
    staging = create_save_staging(destination, "mechpz")
    identity = _row(
        model_revision=3,
        catalogue_id=str(uuid4()),
        producer_node_id="save-1",
        producer_port="report",
        producer_path="[0]",
        producer_iteration=0,
        system_key="standalone",
    )
    identity = {key: identity[key] for key in (
        "schema_version", "model_revision", "producer_iteration", "catalogue_id",
        "producer_node_id", "producer_port", "producer_path", "run_id", "session_id",
        "document_id", "source_key", "system_key",
    )}
    args = {
        "format": "mechpz",
        "source_path": str(source),
        "destination_path": str(destination),
        "work_path": str(work),
        "stage_path": str(staging.primary),
        "stage_companion": "",
        "verify_path": str(staging.verify_project),
        "files": [str(destination)],
        "overwrite": False,
        "catalogue_identity": identity,
        "view_export_path": str(tmp_path / "views.xml"),
        "include_results": False,
        "include_user_files": True,
    }
    result = backend.standalone_save(args)
    assert result["native_save"]["user_directory"] == str(work_files / "UserFiles")
    archive_call = next(call for call in project.calls if call[0] == "Archive")
    assert archive_call[3].IncludeResultAndSolutionFiles is False
    assert archive_call[3].IncludeUserFiles is True
    assert next(call for call in project.calls if call[0] == "Unarchive")[1:] == (
        str(staging.primary), str(staging.verify_project), False
    )
    receipt = json.loads(next(
        row["message"] for row in result["rows"] if row["record_kind"] == "operation"
    ))
    assert receipt["archive_policy"]["exclusions"] == ["result/solution files"]
    assert receipt["archive_policy"]["complete"] is False
    assert receipt["archive_policy"]["result_roots_checked"] == 1
    assert receipt["archive_policy"]["result_files_checked"] == 1
    assert receipt["archive_policy"]["user_roots_checked"] == 1
    assert receipt["archive_policy"]["user_files_checked"] == 1
    assert project.FilePath == str(work)
    assert len(disposed_readers) == 2

    fail_dispose[0] = True
    dispose_error = create_save_staging(destination, "mechpz")
    assert backend.standalone_save({
        **args,
        "stage_path": str(dispose_error.primary),
        "verify_path": str(dispose_error.verify_project),
    })["status"] == "staged"
    assert len(disposed_readers) == 4
    fail_dispose[0] = False

    analysis.ResultFileName = str(work_files / "Modal" / "missing.rst")
    analysis.GetResultsData = lambda: None
    missing_requested = create_save_staging(destination, "mechpz")
    with pytest.raises(RuntimeError, match="requested solved result resources are missing"):
        backend.standalone_save({
            **args,
            "stage_path": str(missing_requested.primary),
            "verify_path": str(missing_requested.verify_project),
            "include_results": True,
        })
    project.UserFiles = None
    missing_user = create_save_staging(destination, "mechpz")
    with pytest.raises(RuntimeError, match=r"Project.UserFiles returned no usable path \(none\)"):
        backend.standalone_save({
            **args,
            "stage_path": str(missing_user.primary),
            "verify_path": str(missing_user.verify_project),
        })
    project.UserFiles = str(work_files / "UserFiles")
    native_model.Analyses = [SimpleNamespace(
        ObjectId=7,
        WorkingDir=None,
        ResultFileName="",
        Solution=SimpleNamespace(Status="NotSolved"),
        GetResultsData=lambda: None,
    )]
    missing_result_root = create_save_staging(destination, "mechpz")
    with pytest.raises(RuntimeError, match=r"WorkingDir returned no usable path: 7 \(none\)"):
        backend.standalone_save({
            **args,
            "stage_path": str(missing_result_root.primary),
            "verify_path": str(missing_result_root.verify_project),
        })
