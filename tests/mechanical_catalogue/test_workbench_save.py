# Purpose: Verify native whole-Workbench save/archive, reconnect, and shared publication safety.
# Map: subsystems/addons.md
# Tests: this file
# Landmarks: _semantic_evidence; test_backend_uses_string_file_inventory_then_flushes_and_reconnects; _state_evidence

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import zipfile
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

from ea_node_editor.addons.mechanical.backend import MechanicalOwnerBackend
from ea_node_editor.addons.mechanical.contracts import catalogue_table, model_handle
from ea_node_editor.addons.mechanical.property_edit import MechanicalPropertyEditAdapter
from ea_node_editor.addons.mechanical.runtime import execute_save_model
from ea_node_editor.addons.mechanical.saving import (
    companion_path,
    create_save_staging,
    validate_workbench_archive_structure,
)
from ea_node_editor.addons.mechanical.session import StaleMechanicalModelError
from ea_node_editor.addons.mechanical.workbench import (
    WORKBENCH_SAVE_BODY,
    validate_workbench_semantic_snapshots,
    validate_workbench_save_receipt,
)
from ea_node_editor.addons.property_edit_adapters import PropertyEditAdapterContext
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.execution_context import ExecutionContext
from tests.mechanical_catalogue.test_contracts import _model_metadata, _row


SAVE_DATA_TYPES = build_default_registry(
    include_public_plugins=False,
    addon_runtime_config=(("mechanical.corex", True),),
).data_types


def _project(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<?xml version='1.0'?><Storage><Project /></Storage>", encoding="utf-8")
    companion = companion_path(path, "wbpj")
    assert companion is not None
    (companion / "dp0" / "SYS" / "MECH").mkdir(parents=True)
    (companion / "dp0" / "SYS" / "MECH" / "file.rst").write_bytes(b"result")
    (companion / "user_files").mkdir()
    (companion / "user_files" / "marker.txt").write_bytes(b"user")
    (companion / "import_files").mkdir()
    (companion / "import_files" / "fixture.step").write_bytes(b"external")
    (companion / "dp0" / "global" / "MECH").mkdir(parents=True)
    (companion / "dp0" / "global" / "MECH" / "SYS.mechdb").write_bytes(b"model")
    return path


def _archive_project(
    archive: Path,
    project: Path,
    *,
    results: bool,
    user: bool,
    external: bool,
) -> None:
    companion = companion_path(project, "wbpj")
    assert companion is not None
    with zipfile.ZipFile(archive, "w") as stream:
        stream.write(project, project.name)
        for path in companion.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(companion).as_posix()
            if (
                relative == "dp0/SYS/MECH/file.rst" and not results
                or relative == "user_files/marker.txt" and not user
                or relative == "import_files/fixture.step" and not external
            ):
                continue
            stream.write(path, f"{project.stem}_files/{relative}")


@pytest.mark.parametrize("format_code", ["wbpj", "wbpz"])
def test_workbench_staging_uses_compact_distinct_native_and_verify_paths(
    tmp_path: Path, format_code: str
) -> None:
    staging = create_save_staging(tmp_path / f"saved.{format_code}", format_code)
    assert staging.primary.parent == staging.root
    assert staging.verify_project == staging.root / "v" / "v.wbpj"
    if format_code == "wbpj":
        assert staging.native_project == staging.primary
        assert staging.companion == staging.root / "s_files"
    else:
        assert staging.native_project == staging.root / "p" / "p.wbpj"
        assert staging.companion is None


@pytest.mark.parametrize(
    ("results", "user", "external"),
    [(True, True, True), (False, True, True), (True, False, True), (True, True, False)],
)
def test_workbench_archive_each_inclusion_is_checked_independently(
    tmp_path: Path, results: bool, user: bool, external: bool
) -> None:
    project = _project(tmp_path / "p.wbpj")
    archive = tmp_path / "p.wbpz"
    _archive_project(archive, project, results=results, user=user, external=external)
    assert validate_workbench_archive_structure(archive)["archive_member_count"] > 1


def _semantic_file(name: str, location: Path, *, associations=()) -> dict[str, object]:
    return {
        "file_name": name,
        "display_text": name,
        "location": str(location),
        "location_key": os.path.normcase(os.path.abspath(location)),
        "registered": bool(associations),
        "exists": True,
        "size": location.stat().st_size,
        "sha256": hashlib.sha256(location.read_bytes()).hexdigest(),
        "associations": list(associations),
    }


def _semantic_snapshot(project: Path, files: list[dict[str, object]]) -> dict[str, object]:
    return {
        "project_file": str(project),
        "project_directory": str(project.parent),
        "user_files_directory": str(project.with_name(project.stem + "_files") / "user_files"),
        "files": files,
        "systems": [
            {"user_id": "system-1", "name": "SYS Ω", "components": [{"user_id": "component-1", "directory_name": "SYS"}]},
            {"user_id": "system-2", "name": "SYS 1", "components": [{"user_id": "component-2", "directory_name": "SYS-1"}]},
            {"user_id": "system-3", "name": "SYS 2", "components": [{"user_id": "component-3", "directory_name": "SYS-2"}]},
        ],
        "models": [
            {"system_user_id": "system-1", "file_name": "SYS.mechdb", "model_id": "shared", "prototype_id": "prototype-shared"},
            {"system_user_id": "system-2", "file_name": "SYS.mechdb", "model_id": "shared", "prototype_id": "prototype-shared"},
            {"system_user_id": "system-3", "file_name": "SYS-2.mechdb", "model_id": "independent", "prototype_id": "prototype-independent"},
        ],
        "parameters": [{
            "display_text": "P³", "expression": "22 °C \\ literal",
            "usage": "Input", "quantity_name": "Length",
        }],
        "design_points": [{
            "display_text": "0", "exported": False, "retained": True,
            "with_files": True, "has_valid_retained_data": True,
            "is_up_to_date": True, "state_of_parameters": "UpToDate",
            "update_order": 0.5,
            "values": [{
                "parameter": {
                    "display_text": "P³", "expression": "22 °C \\ literal",
                    "usage": "Input", "quantity_name": "Length",
                },
                "value": "漢字\\value",
            }],
        }],
    }


def _semantic_evidence(
    tmp_path: Path,
    *,
    stage_files: list[dict[str, object]],
    verify_files: list[dict[str, object]],
) -> tuple[Path, dict[str, object], Path, Path, Path]:
    work = tmp_path / "w.wbpj"
    project = tmp_path / "p.wbpj"
    verify = tmp_path / "v.wbpj"

    def relocated(
        rows: list[dict[str, object]], destination: Path
    ) -> list[dict[str, object]]:
        source_root = project.with_name("p_files")
        destination_root = destination.with_name(destination.stem + "_files")
        relocated_rows: list[dict[str, object]] = []
        for row in rows:
            updated = dict(row)
            try:
                relative = Path(str(row["location"])).relative_to(source_root)
            except ValueError:
                relocated_rows.append(updated)
                continue
            location = destination_root / relative
            updated["location"] = str(location)
            updated["location_key"] = os.path.normcase(os.path.abspath(location))
            relocated_rows.append(updated)
        return relocated_rows

    snapshots = {
        "before": _semantic_snapshot(work, relocated(stage_files, work)),
        "working": _semantic_snapshot(work, relocated(stage_files, work)),
        "stage": _semantic_snapshot(project, stage_files),
        "verify": _semantic_snapshot(verify, relocated(verify_files, verify)),
        "restore": _semantic_snapshot(work, relocated(stage_files, work)),
    }
    payload = json.dumps(
        {"schema_version": 2, "snapshots": snapshots},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    path = tmp_path / "w.json"
    path.write_bytes(payload)
    receipt = _receipt("wbpz")
    receipt.update(
        snapshot_bytes=len(payload),
        snapshot_sha256=hashlib.sha256(payload).hexdigest(),
    )
    return path, receipt, work, project, verify


def test_retained_261_project_path_shape_uses_parent_and_companion_user_files(
    tmp_path: Path,
) -> None:
    root = tmp_path / "T14"
    work = root / "w-b1a754-00" / "source_linked.wbpj"
    stage = root / "a-b1a75487" / ".corex-wbpj-ox0m6h2x" / "s.wbpj"
    before_primary = {
        **_semantic_file("source_linked.wbpj", _project(work)),
        "size": 73_780,
        "sha256": "1" * 64,
        "registered": True,
    }
    restore_primary = {
        **before_primary,
        "size": 73_946,
        "sha256": "2" * 64,
    }
    stage_primary = {
        **_semantic_file("s.wbpj", _project(stage)),
        "size": 73_934,
        "sha256": "3" * 64,
        "registered": True,
    }
    work_act = work.with_name("source_linked_files") / "dp0" / "act.dat"
    work_act.write_bytes(b"act")
    before_act = {
        **_semantic_file("act.dat", work_act),
        "size": 265_640,
        "sha256": "4" * 64,
        "registered": True,
    }
    stage_act = {
        **before_act,
        "location": str(stage.with_name("s_files") / "dp0" / "act.dat"),
        "location_key": os.path.normcase(
            os.path.abspath(stage.with_name("s_files") / "dp0" / "act.dat")
        ),
        "sha256": "5" * 64,
    }
    restore_act = {
        **stage_act,
        "location": str(work.with_name("source_linked_files") / "dp0" / "act.dat"),
        "location_key": os.path.normcase(
            os.path.abspath(work.with_name("source_linked_files") / "dp0" / "act.dat")
        ),
    }
    snapshots = {
        "before": _semantic_snapshot(work, [before_primary, before_act]),
        "working": _semantic_snapshot(work, [restore_primary, restore_act]),
        "stage": _semantic_snapshot(stage, [stage_primary, stage_act]),
        "verify": _semantic_snapshot(stage, [stage_primary, stage_act]),
        "restore": _semantic_snapshot(work, [restore_primary, restore_act]),
    }
    payload = json.dumps(
        {"schema_version": 2, "snapshots": snapshots},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    snapshot_path = tmp_path / "w.json"
    snapshot_path.write_bytes(payload)
    receipt = _receipt("wbpj")
    receipt.update(
        snapshot_bytes=len(payload),
        snapshot_sha256=hashlib.sha256(payload).hexdigest(),
    )

    proof = validate_workbench_semantic_snapshots(
        snapshot_path,
        receipt=receipt,
        format_code="wbpj",
        work_path=work,
        native_project=stage,
        stage_path=stage,
        verify_path=root / "unused.wbpj",
    )

    assert snapshots["before"]["project_directory"] == str(work.parent)
    assert snapshots["before"]["user_files_directory"] == str(
        work.with_name("source_linked_files") / "user_files"
    )
    assert snapshots["stage"]["project_directory"] == str(stage.parent)
    assert snapshots["stage"]["user_files_directory"] == str(
        stage.with_name("s_files") / "user_files"
    )
    assert proof["system_count"] == 3


def test_same_attested_primary_path_rejects_changed_bytes(tmp_path: Path) -> None:
    path, receipt, work, project, verify = _semantic_evidence(
        tmp_path, stage_files=[], verify_files=[]
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    primary = {
        "file_name": project.name,
        "display_text": project.name,
        "location": str(project),
        "location_key": os.path.normcase(os.path.abspath(project)),
        "registered": True,
        "exists": True,
        "size": 100,
        "sha256": "1" * 64,
        "associations": [],
    }
    payload["snapshots"]["stage"]["files"] = [primary]
    payload["snapshots"]["verify"] = dict(payload["snapshots"]["stage"])
    payload["snapshots"]["verify"]["files"] = [
        {**primary, "size": 101, "sha256": "2" * 64}
    ]
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    path.write_bytes(encoded)
    receipt.update(
        format="wbpj",
        companion_exists=True,
        snapshot_bytes=len(encoded),
        snapshot_sha256=hashlib.sha256(encoded).hexdigest(),
    )

    with pytest.raises(RuntimeError, match="inventory changed during verify"):
        validate_workbench_semantic_snapshots(
            path,
            receipt=receipt,
            format_code="wbpj",
            work_path=work,
            native_project=project,
            stage_path=project,
            verify_path=verify,
        )


def test_same_working_primary_path_rejects_changed_restore_bytes(
    tmp_path: Path,
) -> None:
    path, receipt, work, project, verify = _semantic_evidence(
        tmp_path, stage_files=[], verify_files=[]
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    def primary(location: Path, digest: str) -> dict[str, object]:
        return {
            "file_name": location.name,
            "display_text": location.name,
            "location": str(location),
            "location_key": os.path.normcase(os.path.abspath(location)),
            "registered": True,
            "exists": True,
            "size": 100,
            "sha256": digest,
            "associations": [],
        }

    payload["snapshots"]["working"]["files"] = [primary(work, "1" * 64)]
    payload["snapshots"]["stage"]["files"] = [primary(project, "2" * 64)]
    payload["snapshots"]["verify"]["files"] = [primary(verify, "3" * 64)]
    payload["snapshots"]["restore"]["files"] = [primary(work, "4" * 64)]
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    path.write_bytes(encoded)
    receipt.update(
        snapshot_bytes=len(encoded),
        snapshot_sha256=hashlib.sha256(encoded).hexdigest(),
    )

    with pytest.raises(RuntimeError, match="inventory changed during restore"):
        validate_workbench_semantic_snapshots(
            path,
            receipt=receipt,
            format_code="wbpz",
            work_path=work,
            native_project=project,
            stage_path=project,
            verify_path=verify,
        )


def test_changed_post_flush_companion_asset_fails_during_save_as(
    tmp_path: Path,
) -> None:
    companion = tmp_path / "p_files"
    companion.mkdir()
    asset = companion / "act.dat"
    asset.write_bytes(b"working asset")
    row = _semantic_file("act.dat", asset)
    path, receipt, work, project, verify = _semantic_evidence(
        tmp_path, stage_files=[row], verify_files=[row]
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["snapshots"]["stage"]["files"][0].update(
        size=14,
        sha256=hashlib.sha256(b"changed asset!").hexdigest(),
    )
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    path.write_bytes(encoded)
    receipt.update(
        snapshot_bytes=len(encoded),
        snapshot_sha256=hashlib.sha256(encoded).hexdigest(),
    )

    with pytest.raises(RuntimeError, match="inventory changed during stage"):
        validate_workbench_semantic_snapshots(
            path,
            receipt=receipt,
            format_code="wbpz",
            work_path=work,
            native_project=project,
            stage_path=project,
            verify_path=verify,
        )


def _external_rebase_rows(
    tmp_path: Path, *, directory: str = "import_files", targets: int = 1
) -> tuple[dict[str, object], list[dict[str, object]]]:
    external = tmp_path / "beside.step"
    external.write_bytes(b"registered external")
    stage_row = _semantic_file(
        "beside.step", external, associations=("system-1|component-1",)
    )
    verify_root = tmp_path / "v_files" / directory
    rows = []
    for index in range(targets):
        location = verify_root / ((f"copy-{index}/beside.step") if targets > 1 else "beside.step")
        rows.append({
            **stage_row,
            "location": str(location),
            "location_key": os.path.normcase(os.path.abspath(location)),
        })
    return stage_row, rows


def test_registered_external_beside_project_keeps_exact_native_location(
    tmp_path: Path,
) -> None:
    external = tmp_path / "beside.step"
    external.write_bytes(b"registered external")
    row = _semantic_file(
        "beside.step", external, associations=("system-1|component-1",)
    )
    path, receipt, work, project, verify = _semantic_evidence(
        tmp_path, stage_files=[row], verify_files=[]
    )

    proof = validate_workbench_semantic_snapshots(
        path,
        receipt=receipt,
        format_code="wbpz",
        work_path=work,
        native_project=project,
        stage_path=project,
        verify_path=verify,
        include_external_imported_files=False,
    )
    assert proof["registered_file_count"] == 1
    with pytest.raises(RuntimeError, match="external archive rebase"):
        validate_workbench_semantic_snapshots(
            path,
            receipt=receipt,
            format_code="wbpz",
            work_path=work,
            native_project=project,
            stage_path=project,
            verify_path=verify,
            include_external_imported_files=True,
        )


def test_archive_reopen_rebases_registered_external_with_exact_payload_identity(
    tmp_path: Path,
) -> None:
    stage_row, verify_rows = _external_rebase_rows(tmp_path)
    path, receipt, work, project, verify = _semantic_evidence(
        tmp_path, stage_files=[stage_row], verify_files=verify_rows
    )

    proof = validate_workbench_semantic_snapshots(
        path,
        receipt=receipt,
        format_code="wbpz",
        work_path=work,
        native_project=project,
        stage_path=project,
        verify_path=verify,
        include_external_imported_files=True,
    )
    assert proof["required_file_count"] == 1
    assert proof["external_rebase_count"] == 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["snapshots"]["verify"]["files"][0]["sha256"] = "f" * 64
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    path.write_bytes(encoded)
    receipt.update(
        snapshot_bytes=len(encoded),
        snapshot_sha256=hashlib.sha256(encoded).hexdigest(),
    )
    with pytest.raises(RuntimeError, match="external archive rebase"):
        validate_workbench_semantic_snapshots(
            path,
            receipt=receipt,
            format_code="wbpz",
            work_path=work,
            native_project=project,
            stage_path=project,
            verify_path=verify,
            include_external_imported_files=True,
        )


def test_archive_external_rebase_rejects_ambiguous_targets(tmp_path: Path) -> None:
    stage_row, verify_rows = _external_rebase_rows(tmp_path, targets=2)
    path, receipt, work, project, verify = _semantic_evidence(
        tmp_path, stage_files=[stage_row], verify_files=verify_rows
    )
    with pytest.raises(RuntimeError, match="external archive rebase.*ambiguous"):
        validate_workbench_semantic_snapshots(
            path,
            receipt=receipt,
            format_code="wbpz",
            work_path=work,
            native_project=project,
            stage_path=project,
            verify_path=verify,
        )


def test_archive_external_rebase_does_not_reuse_existing_import_row(
    tmp_path: Path,
) -> None:
    stage_import = tmp_path / "p_files" / "import_files" / "same.step"
    external = tmp_path / "outside" / "same.step"
    stage_import.parent.mkdir(parents=True)
    external.parent.mkdir()
    stage_import.write_bytes(b"overlapping payload")
    external.write_bytes(b"overlapping payload")
    associations = ("system-1|component-1",)
    companion_row = _semantic_file("same.step", stage_import, associations=associations)
    external_row = _semantic_file("same.step", external, associations=associations)
    verify_location = tmp_path / "v_files" / "import_files" / "same.step"
    verify_row = {
        **companion_row,
        "location": str(verify_location),
        "location_key": os.path.normcase(os.path.abspath(verify_location)),
    }
    path, receipt, work, project, verify = _semantic_evidence(
        tmp_path,
        stage_files=[companion_row, external_row],
        verify_files=[verify_row],
    )
    with pytest.raises(RuntimeError, match="external archive rebase"):
        validate_workbench_semantic_snapshots(
            path,
            receipt=receipt,
            format_code="wbpz",
            work_path=work,
            native_project=project,
            stage_path=project,
            verify_path=verify,
        )


def test_archive_external_rebase_rejects_two_rows_at_one_normalized_location(
    tmp_path: Path,
) -> None:
    stage_import = tmp_path / "p_files" / "import_files" / "same.step"
    external = tmp_path / "outside" / "same.step"
    stage_import.parent.mkdir(parents=True)
    external.parent.mkdir()
    stage_import.write_bytes(b"overlapping payload")
    external.write_bytes(b"overlapping payload")
    associations = ("system-1|component-1",)
    companion_row = _semantic_file("same.step", stage_import, associations=associations)
    external_row = _semantic_file("same.step", external, associations=associations)
    verify_location = tmp_path / "v_files" / "import_files" / "same.step"
    alternate_spelling = str(verify_location).upper().replace("\\", "/")
    verify_rows = [
        {
            **companion_row,
            "location": str(verify_location),
            "location_key": os.path.normcase(os.path.abspath(verify_location)),
        },
        {
            **external_row,
            "location": alternate_spelling,
            "location_key": os.path.normcase(os.path.abspath(alternate_spelling)),
        },
    ]
    path, receipt, work, project, verify = _semantic_evidence(
        tmp_path,
        stage_files=[companion_row, external_row],
        verify_files=verify_rows,
    )
    with pytest.raises(RuntimeError, match="file locations are ambiguous"):
        validate_workbench_semantic_snapshots(
            path,
            receipt=receipt,
            format_code="wbpz",
            work_path=work,
            native_project=project,
            stage_path=project,
            verify_path=verify,
        )


def test_archive_external_rebase_rejects_duplicate_source_payloads(
    tmp_path: Path,
) -> None:
    first = tmp_path / "one" / "same.step"
    second = tmp_path / "two" / "same.step"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"same external")
    second.write_bytes(b"same external")
    stage_rows = [
        _semantic_file("same.step", path, associations=("system-1|component-1",))
        for path in (first, second)
    ]
    verify_rows = [
        {
            **row,
            "location": str(tmp_path / "v_files" / "import_files" / str(index) / "same.step"),
            "location_key": os.path.normcase(
                os.path.abspath(tmp_path / "v_files" / "import_files" / str(index) / "same.step")
            ),
        }
        for index, row in enumerate(stage_rows)
    ]
    path, receipt, work, project, verify = _semantic_evidence(
        tmp_path, stage_files=stage_rows, verify_files=verify_rows
    )
    with pytest.raises(RuntimeError, match="external archive mapping is ambiguous"):
        validate_workbench_semantic_snapshots(
            path,
            receipt=receipt,
            format_code="wbpz",
            work_path=work,
            native_project=project,
            stage_path=project,
            verify_path=verify,
        )


def test_archive_external_rebase_rejects_changed_associations(tmp_path: Path) -> None:
    stage_row, verify_rows = _external_rebase_rows(tmp_path)
    verify_rows[0]["associations"] = ["system-2|component-2"]
    path, receipt, work, project, verify = _semantic_evidence(
        tmp_path, stage_files=[stage_row], verify_files=verify_rows
    )
    with pytest.raises(RuntimeError, match="external archive rebase"):
        validate_workbench_semantic_snapshots(
            path,
            receipt=receipt,
            format_code="wbpz",
            work_path=work,
            native_project=project,
            stage_path=project,
            verify_path=verify,
        )


def test_archive_external_rebase_rejects_wrong_storage(tmp_path: Path) -> None:
    stage_row, verify_rows = _external_rebase_rows(tmp_path, directory="other")
    path, receipt, work, project, verify = _semantic_evidence(
        tmp_path, stage_files=[stage_row], verify_files=verify_rows
    )
    with pytest.raises(RuntimeError, match="external archive rebase"):
        validate_workbench_semantic_snapshots(
            path,
            receipt=receipt,
            format_code="wbpz",
            work_path=work,
            native_project=project,
            stage_path=project,
            verify_path=verify,
        )


def test_archive_external_rebase_rejects_exclusion_off_presence(tmp_path: Path) -> None:
    stage_row, verify_rows = _external_rebase_rows(tmp_path)
    path, receipt, work, project, verify = _semantic_evidence(
        tmp_path, stage_files=[stage_row], verify_files=verify_rows
    )
    with pytest.raises(RuntimeError, match="excluded registered external file"):
        validate_workbench_semantic_snapshots(
            path,
            receipt=receipt,
            format_code="wbpz",
            work_path=work,
            native_project=project,
            stage_path=project,
            verify_path=verify,
            include_external_imported_files=False,
        )


@pytest.mark.parametrize("mutation", ["content", "associations"])
def test_archive_external_exclusion_rejects_mutated_new_import(
    tmp_path: Path, mutation: str
) -> None:
    stage_row, verify_rows = _external_rebase_rows(tmp_path)
    if mutation == "content":
        verify_rows[0].update(size=99, sha256="f" * 64)
    else:
        verify_rows[0]["associations"] = ["system-2|component-2"]
    path, receipt, work, project, verify = _semantic_evidence(
        tmp_path, stage_files=[stage_row], verify_files=verify_rows
    )
    with pytest.raises(RuntimeError, match="excluded registered external file"):
        validate_workbench_semantic_snapshots(
            path,
            receipt=receipt,
            format_code="wbpz",
            work_path=work,
            native_project=project,
            stage_path=project,
            verify_path=verify,
            include_external_imported_files=False,
        )


def test_archive_external_rebase_is_never_allowed_for_wbpj(tmp_path: Path) -> None:
    stage_row, verify_rows = _external_rebase_rows(tmp_path)
    path, receipt, work, project, verify = _semantic_evidence(
        tmp_path, stage_files=[stage_row], verify_files=verify_rows
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    snapshot = payload["snapshots"]["verify"]
    snapshot.update(
        project_file=str(project),
        project_directory=str(project.parent),
        user_files_directory=str(project.with_name("p_files") / "user_files"),
    )
    location = project.with_name("p_files") / "import_files" / "beside.step"
    snapshot["files"][0].update(
        location=str(location),
        location_key=os.path.normcase(os.path.abspath(location)),
    )
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    path.write_bytes(encoded)
    receipt.update(
        format="wbpj",
        companion_exists=True,
        snapshot_bytes=len(encoded),
        snapshot_sha256=hashlib.sha256(encoded).hexdigest(),
    )
    with pytest.raises(RuntimeError, match="inventory changed during verify"):
        validate_workbench_semantic_snapshots(
            path,
            receipt=receipt,
            format_code="wbpj",
            work_path=work,
            native_project=project,
            stage_path=project,
            verify_path=verify,
        )


def test_no_results_preserves_required_mechanical_setup_payload(tmp_path: Path) -> None:
    project = _project(tmp_path / "p.wbpj")
    companion = companion_path(project, "wbpj")
    assert companion is not None
    setup = companion / "dp0/SYS/MECH/Setup/required.pmdb"
    setup.parent.mkdir(parents=True)
    setup.write_bytes(b"required setup")
    row = _semantic_file("required.pmdb", setup, associations=("system-1|component-1",))
    path, receipt, work, project, verify = _semantic_evidence(
        tmp_path, stage_files=[row], verify_files=[row]
    )
    proof = validate_workbench_semantic_snapshots(
        path,
        receipt=receipt,
        format_code="wbpz",
        work_path=work,
        native_project=project,
        stage_path=project,
        verify_path=verify,
        include_results=False,
        include_user_files=True,
        include_external_imported_files=True,
    )
    assert proof["shared_model_group_count"] == 1
    nested = json.loads(path.read_bytes().decode("utf-8"))["snapshots"]["verify"]
    assert nested["systems"][0]["name"] == "SYS Ω"
    assert nested["parameters"][0]["expression"] == "22 °C \\ literal"
    assert nested["design_points"][0]["values"][0]["value"] == "漢字\\value"


def test_archive_rejects_missing_required_asset_with_unchanged_system_identity(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path / "p.wbpj")
    companion = companion_path(project, "wbpj")
    assert companion is not None
    required = companion / "required.bin"
    required.write_bytes(b"required unclassified component asset")
    row = _semantic_file("required.bin", required, associations=("system-1|component-1",))
    path, receipt, work, project, verify = _semantic_evidence(
        tmp_path, stage_files=[row], verify_files=[]
    )
    with pytest.raises(RuntimeError, match="required Workbench project inventory"):
        validate_workbench_semantic_snapshots(
            path,
            receipt=receipt,
            format_code="wbpz",
            work_path=work,
            native_project=project,
            stage_path=project,
            verify_path=verify,
            include_results=False,
            include_user_files=True,
            include_external_imported_files=True,
        )


@pytest.mark.parametrize("semantic_key", ["models", "design_points", "parameters"])
def test_semantic_snapshot_rejects_changed_model_design_point_or_parameter(
    tmp_path: Path, semantic_key: str
) -> None:
    path, receipt, work, project, verify = _semantic_evidence(
        tmp_path, stage_files=[], verify_files=[]
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if semantic_key == "models":
        payload["snapshots"]["verify"]["models"][1]["model_id"] = "severed"
    elif semantic_key == "design_points":
        payload["snapshots"]["verify"]["design_points"][0]["update_order"] = 0.75
    else:
        changed = payload["snapshots"]["verify"]["parameters"][0]
        changed["display_text"] = "P2"
        payload["snapshots"]["verify"]["design_points"][0]["values"][0]["parameter"] = changed
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    path.write_bytes(encoded)
    receipt.update(
        snapshot_bytes=len(encoded),
        snapshot_sha256=hashlib.sha256(encoded).hexdigest(),
    )
    with pytest.raises(RuntimeError, match=semantic_key):
        validate_workbench_semantic_snapshots(
            path,
            receipt=receipt,
            format_code="wbpz",
            work_path=work,
            native_project=project,
            stage_path=project,
            verify_path=verify,
        )


def test_semantic_snapshot_rejects_restore_left_on_equivalent_staging_project(
    tmp_path: Path,
) -> None:
    path, receipt, work, project, verify = _semantic_evidence(
        tmp_path, stage_files=[], verify_files=[]
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["snapshots"]["restore"].update(
        project_file=str(project),
        project_directory=str(project.parent),
        user_files_directory=str(project.with_name("p_files") / "user_files"),
    )
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    path.write_bytes(encoded)
    receipt.update(
        snapshot_bytes=len(encoded),
        snapshot_sha256=hashlib.sha256(encoded).hexdigest(),
    )
    with pytest.raises(RuntimeError, match="restore phase path attestation"):
        validate_workbench_semantic_snapshots(
            path,
            receipt=receipt,
            format_code="wbpz",
            work_path=work,
            native_project=project,
            stage_path=project,
            verify_path=verify,
        )


def test_semantic_snapshot_preserves_duplicate_basenames_by_native_locations(
    tmp_path: Path,
) -> None:
    first = tmp_path / "one" / "same.dat"
    second = tmp_path / "two" / "same.dat"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    rows = [
        _semantic_file("same.dat", first, associations=("system-1|component-1",)),
        _semantic_file("same.dat", second, associations=("system-1|component-1",)),
    ]
    verify_rows = [
        {
            **row,
            "location": str(tmp_path / "v_files" / "import_files" / str(index) / "same.dat"),
            "location_key": os.path.normcase(
                os.path.abspath(tmp_path / "v_files" / "import_files" / str(index) / "same.dat")
            ),
        }
        for index, row in enumerate(rows)
    ]
    path, receipt, work, project, verify = _semantic_evidence(
        tmp_path, stage_files=rows, verify_files=verify_rows
    )
    proof = validate_workbench_semantic_snapshots(
        path,
        receipt=receipt,
        format_code="wbpz",
        work_path=work,
        native_project=project,
        stage_path=project,
        verify_path=verify,
        include_results=False,
    )
    assert proof["required_file_count"] == 2
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["snapshots"]["verify"]["files"].pop()
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    path.write_bytes(encoded)
    receipt.update(
        snapshot_bytes=len(encoded),
        snapshot_sha256=hashlib.sha256(encoded).hexdigest(),
    )
    with pytest.raises(RuntimeError, match="external archive rebase"):
        validate_workbench_semantic_snapshots(
            path,
            receipt=receipt,
            format_code="wbpz",
            work_path=work,
            native_project=project,
            stage_path=project,
            verify_path=verify,
            include_results=False,
        )


def test_semantic_snapshot_rejects_windows_reparse_before_reading(
    tmp_path: Path, monkeypatch
) -> None:
    path, receipt, work, project, verify = _semantic_evidence(
        tmp_path, stage_files=[], verify_files=[]
    )
    monkeypatch.setattr(
        "ea_node_editor.addons.mechanical.workbench.is_reparse_point",
        lambda candidate: candidate == path,
    )
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda _path: (_ for _ in ()).throw(AssertionError("reparse payload was read")),
    )
    with pytest.raises(RuntimeError, match="snapshot file is invalid"):
        validate_workbench_semantic_snapshots(
            path,
            receipt=receipt,
            format_code="wbpz",
            work_path=work,
            native_project=project,
            stage_path=project,
            verify_path=verify,
        )


def _receipt(format_code: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "marker": "corex-workbench-save-v1",
        "ok": True,
        "format": format_code,
        "snapshot_count": 5,
        "snapshot_bytes": 2,
        "snapshot_sha256": "a" * 64,
        "primary_exists": True,
        "companion_exists": format_code == "wbpj",
        "error_type": "",
        "error_digest": "",
    }


def test_workbench_receipt_is_strict_bounded_and_never_accepts_none() -> None:
    assert validate_workbench_save_receipt(
        _receipt("wbpz"), format_code="wbpz"
    )["ok"] is True
    for value in (None, {**_receipt("wbpz"), "extra": 1}):
        with pytest.raises(RuntimeError, match="invalid bounded receipt"):
            validate_workbench_save_receipt(value, format_code="wbpz")
    failed = {**_receipt("wbpz"), "ok": False, "error_type": "NativeError", "error_digest": "b" * 64}
    with pytest.raises(RuntimeError, match="NativeError"):
        validate_workbench_save_receipt(failed, format_code="wbpz")
    for digest in ("same", "A" * 64, "g" * 64, "0" * 63):
        invalid = {
            **_receipt("wbpz"),
            "snapshot_sha256": digest,
        }
        with pytest.raises(RuntimeError, match="receipt digest is invalid"):
            validate_workbench_save_receipt(
                invalid, format_code="wbpz"
            )


def test_native_script_uses_only_workbench_project_lifecycle_and_formal_archive_keywords() -> None:
    assert "Exit(SaveDatabase=True)" in WORKBENCH_SAVE_BODY
    assert "Save(FilePath=native_project,Overwrite=False)" in WORKBENCH_SAVE_BODY
    assert "FailIfMissingFiles=True" in WORKBENCH_SAVE_BODY
    assert "Unarchive(ArchivePath=stage,ProjectPath=verify,Overwrite=False)" in WORKBENCH_SAVE_BODY
    assert "dsdb" not in WORKBENCH_SAVE_BODY.casefold()
    assert "copy" not in WORKBENCH_SAVE_BODY.casefold()


def test_native_snapshot_order_captures_post_flush_work_before_save_as() -> None:
    markers = (
        "snapshots['before']=_corex_snapshot()",
        "container.Exit(SaveDatabase=True)",
        "Save()",
        "snapshots['working']=_corex_snapshot()",
        "Save(FilePath=native_project,Overwrite=False)",
        "snapshots['stage']=_corex_snapshot()",
        "snapshots['verify']=_corex_snapshot()",
        "Open(FilePath=work);snapshots['restore']=_corex_snapshot()",
    )
    offsets = [WORKBENCH_SAVE_BODY.index(marker) for marker in markers]
    assert offsets == sorted(offsets)


class _Sessions:
    def __init__(self, tmp_path: Path, source: Path):
        self.session = SimpleNamespace(
            revision=2,
            connection_generation=4,
            work_root=tmp_path,
            work_path=_project(tmp_path / "w.wbpj"),
            source_path=source,
            terminal=False,
        )
        self.calls: list[dict[str, object]] = []

    def admit_model(self, model, **_kwargs):
        if (
            model.metadata["model_revision"] != self.session.revision
            or model.metadata["connection_generation"] != self.session.connection_generation
        ):
            raise StaleMechanicalModelError("stale")
        return self.session

    def operate(self, _session, **kwargs):
        self.calls.append(kwargs)
        self.session.revision += 1
        self.session.connection_generation += 1
        args = kwargs["args"]
        stage = Path(args["stage_path"])
        if args["format"] == "wbpj":
            _project(stage)
        else:
            native_project = _project(Path(args["native_project"]))
            _archive_project(
                stage,
                native_project,
                results=args["include_results"],
                user=args["include_user_files"],
                external=args["include_external_imported_files"],
            )
        row = _row(
            model_revision=3,
            catalogue_id=args["catalogue_identity"]["catalogue_id"],
            producer_node_id="save-1",
            producer_port="report",
            producer_path="[3,1]",
            producer_iteration=4,
            system_key="SYS",
        )
        return {
            "status": "staged",
            "native_save": _receipt(args["format"]),
            "connection_changed": True,
            "connection_generation": self.session.connection_generation,
            "catalogue": catalogue_table([row]),
        }

    @staticmethod
    def register_model(_session, **kwargs):
        return kwargs

    @staticmethod
    def retire_session(_session):
        return None


def _context(tmp_path: Path, sessions: _Sessions, destination: Path, **properties):
    values = {
        "file": str(destination),
        "format": "auto",
        "include_results": True,
        "include_user_files": True,
        "include_external_imported_files": True,
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


def _model() -> object:
    return model_handle(
        handle_id="model",
        owner_scope="run-1",
        worker_generation=1,
        metadata=_model_metadata(
            model_revision=2,
            connection_generation=4,
            system_key="SYS",
        ),
    )


def test_runtime_wbpj_consumes_no_archive_controls_and_refreshes_connection(tmp_path: Path) -> None:
    source = _project(tmp_path / "source.wbpj")
    sessions = _Sessions(tmp_path / "run", source)
    sessions.session.work_root.mkdir(exist_ok=True)
    destination = tmp_path / "saved.wbpj"
    ctx, invalidations = _context(
        tmp_path,
        sessions,
        destination,
        include_results="inactive",
        include_user_files="inactive",
        include_external_imported_files="inactive",
    )
    result = execute_save_model(ctx, _model(), SimpleNamespace(**ctx.properties))
    call = sessions.calls[0]
    assert call["operation"] == "workbench_save"
    assert call["connection_change"] is True and call["mutation"] is True
    assert not {"include_results", "include_user_files", "include_external_imported_files"} & call["args"].keys()
    assert result["files"] == [str(destination), str(companion_path(destination, "wbpj"))]
    assert result["model"]["producer_node_id"] == "save-1"
    assert invalidations == [("open-1", "mechanical_model_mutated")]
    with pytest.raises(ValueError, match="stale_reference"):
        execute_save_model(ctx, _model(), SimpleNamespace(**ctx.properties))


def test_runtime_wbpz_consumes_all_three_boolean_controls(tmp_path: Path) -> None:
    source = _project(tmp_path / "source.wbpj")
    sessions = _Sessions(tmp_path / "run", source)
    sessions.session.work_root.mkdir(exist_ok=True)
    destination = tmp_path / "saved.wbpz"
    ctx, _invalidations = _context(
        tmp_path,
        sessions,
        destination,
        include_results=False,
        include_user_files=True,
        include_external_imported_files=False,
    )
    result = execute_save_model(ctx, _model(), SimpleNamespace(**ctx.properties))
    args = sessions.calls[0]["args"]
    assert [args[key] for key in ("include_results", "include_user_files", "include_external_imported_files")] == [False, True, False]
    assert result["files"] == [str(destination)]


def test_workbench_mechpz_rejection_points_to_supported_archive_before_staging(tmp_path: Path) -> None:
    source = _project(tmp_path / "source.wbpj")
    sessions = _Sessions(tmp_path / "run", source)
    sessions.session.work_root.mkdir(exist_ok=True)
    ctx, invalidations = _context(tmp_path, sessions, tmp_path / "wrong.mechpz")
    with pytest.raises(ValueError, match=r"choose native whole-project \.wbpz"):
        execute_save_model(ctx, _model(), SimpleNamespace(**ctx.properties))
    assert sessions.calls == [] and invalidations == []


def test_property_metadata_enables_only_applicable_archive_ports() -> None:
    adapter = MechanicalPropertyEditAdapter()
    items = [
        {"key": key, "editor_enabled": True, "condition_enabled": True}
        for key in ("include_results", "include_user_files", "include_external_imported_files")
    ]
    context = PropertyEditAdapterContext(
        node=SimpleNamespace(
            type_id="mechanical.save_model",
            properties={"format": "auto", "file": "saved.wbpz"},
        )
    )
    assert [item["editor_enabled"] for item in adapter.build_property_items(context, items)] == [True, True, True]
    context.node.properties["file"] = "saved.wbpj"
    assert [item["editor_enabled"] for item in adapter.build_property_items(context, items)] == [False, False, False]


class _Container:
    def __init__(self, name: str, calls: list[tuple[object, ...]], model_id: str):
        self.Name = name
        self.calls = calls
        self.model_id = model_id

    def Exit(self, *, SaveDatabase: bool):
        self.calls.append(("Exit", self.Name, SaveDatabase))

    def Edit(self, **kwargs):
        self.calls.append(("Edit", self.Name, kwargs))

    def GetMechanicalModel(self):
        return SimpleNamespace(
            File=SimpleNamespace(FileName=f"{self.Name}.mechdb"),
            ModelId=self.model_id,
            PrototypeId=f"prototype-{self.model_id}",
        )


class _System:
    def __init__(self, name: str, label: str, container: _Container, files):
        self.Name, self.DisplayText, self.container = name, label, container
        self.UserId = f"id-{name}"
        self.Components = [SimpleNamespace(
            UserId="Model" if name == "SYS" else f"Model {name.removeprefix('SYS ')}",
            DirectoryName=name,
            DataContainer=SimpleNamespace(GetFiles=files),
        )]

    def GetContainer(self, *, ComponentName: str):
        assert ComponentName == "Model"
        return self.container


class _ModelLessSystem:
    def __init__(self):
        self.Name = self.UserId = "EXT"
        self.DisplayText = "External Model"
        self.calls = 0
        self.Components = [SimpleNamespace(
            UserId="Setup External",
            DirectoryName="EXT",
            DataContainer=SimpleNamespace(GetFiles=lambda: []),
        )]

    def GetContainer(self, *, ComponentName: str):
        self.calls += 1
        raise AssertionError(f"inapplicable {ComponentName} lookup")


class _Workbench:
    def __init__(self, work: Path):
        self.current = work
        self.calls: list[tuple[object, ...]] = []
        shared = _Container("Model", self.calls, "shared-model")
        independent = _Container("Model 2", self.calls, "independent-model")
        self.systems = [
            _System("SYS", "Primary ³ ° Ω 漢字 \\ path", shared, self._files),
            _System("SYS 1", "Secondary", shared, self._files),
            _System("SYS 2", "Independent", independent, self._files),
            _ModelLessSystem(),
        ]

    def _files(self):
        root = companion_path(self.current, "wbpj")
        assert root is not None
        return [
            SimpleNamespace(
                FileName=path.relative_to(root).as_posix(),
                DisplayText=path.name,
                Location=str(path),
                Exists=path.is_file(),
                Size=path.stat().st_size,
            )
            for path in root.rglob("*")
            if path.is_file()
        ]

    def run_script_string(self, script: str):
        def save(*, FilePath=None, Overwrite=None):
            self.calls.append(("Save", FilePath, Overwrite))
            if FilePath is None:
                return
            destination = Path(FilePath)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.current, destination)
            source_files = companion_path(self.current, "wbpj")
            destination_files = companion_path(destination, "wbpj")
            assert source_files is not None and destination_files is not None
            shutil.copytree(source_files, destination_files)
            self.current = destination

        def open_project(*, FilePath):
            self.calls.append(("Open", FilePath))
            self.current = Path(FilePath)

        def archive(*, FilePath, IncludeSkippedFiles, IncludeUserFiles, IncludeExternalImportedFiles, FailIfMissingFiles):
            self.calls.append(("Archive", IncludeSkippedFiles, IncludeUserFiles, IncludeExternalImportedFiles, FailIfMissingFiles))
            _archive_project(
                Path(FilePath),
                self.current,
                results=IncludeSkippedFiles,
                user=IncludeUserFiles,
                external=IncludeExternalImportedFiles,
            )

        def unarchive(*, ArchivePath, ProjectPath, Overwrite):
            self.calls.append(("Unarchive", ArchivePath, ProjectPath, Overwrite))
            with zipfile.ZipFile(ArchivePath) as stream:
                member = next(name for name in stream.namelist() if name.endswith(".wbpj"))
                Path(ProjectPath).parent.mkdir(parents=True, exist_ok=True)
                Path(ProjectPath).write_bytes(stream.read(member))
                files = companion_path(Path(ProjectPath), "wbpj")
                assert files is not None
                files.mkdir()
                prefix = member[:-5] + "_files/"
                for name in stream.namelist():
                    if name.startswith(prefix) and not name.endswith("/"):
                        target = files / name[len(prefix):]
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(stream.read(name))
            self.current = Path(ProjectPath)

        namespace = {
            "GetAllSystems": lambda: self.systems,
            "GetSystem": lambda *, Name: next(item for item in self.systems if item.Name == Name),
            "Save": save,
            "Open": open_project,
            "Archive": archive,
            "Unarchive": unarchive,
            "GetProjectFile": lambda: str(self.current),
            "GetProjectDirectory": lambda: str(self.current.parent),
            "GetAllFiles": lambda: [ref.Location for ref in self._files()],
            "GetCurrentRegisteredFiles": self._files,
            "GetUserFilesDirectory": lambda: str(companion_path(self.current, "wbpj") / "user_files"),
            "Parameters": SimpleNamespace(
                GetAllParameters=lambda: [],
                GetAllDesignPoints=lambda: [],
                GetAllDesignPointsWithFiles=lambda: [],
                GetAllRetainedDesignPoints=lambda **_kwargs: [],
                GetAllExportedDesignPoints=lambda **_kwargs: [],
            ),
        }
        exec(compile(script, "<workbench-save-test>", "exec"), namespace)
        value = namespace["wb_script_result"]
        return json.loads(value) if isinstance(value, str) else value

    def stop_mechanical_server(self, *, system_name: str):
        self.calls.append(("stop", system_name))


@pytest.mark.parametrize("format_code", ["wbpj", "wbpz"])
def test_backend_uses_string_file_inventory_then_flushes_and_reconnects(
    tmp_path: Path, monkeypatch, format_code: str
) -> None:
    monkeypatch.delattr(os, "fsync", raising=False)
    source = _project(tmp_path / "source.wbpj").resolve()
    work = _project(tmp_path / "work.wbpj").resolve()
    destination = tmp_path / f"published.{format_code}"
    staging = create_save_staging(destination, format_code)
    workbench = _Workbench(work)
    native_run_script = workbench.run_script_string

    def run_without_cpython_only_math_helpers(script: str):
        with monkeypatch.context() as native_environment:
            native_environment.delattr(math, "isfinite", raising=False)
            return native_run_script(script)

    monkeypatch.setattr(workbench, "run_script_string", run_without_cpython_only_math_helpers)
    backend = MechanicalOwnerBackend()
    backend.workbench = workbench
    backend.mechanical = object()
    backend.mechanical_server_started = True
    backend.system_name = "SYS"
    backend.source_path = source
    backend.work_path = work
    backend.work_root = tmp_path.resolve()
    backend.systems = [
        {"key": "SYS", "label": "Primary", "model_key": "Model", "system_keys": ["SYS", "SYS 1"]},
        {"key": "SYS 2", "label": "Independent", "model_key": "Model 2", "system_keys": ["SYS 2"]},
    ]

    def reconnect():
        workbench.calls.append(("reconnect", backend.system_name))
        backend.mechanical_server_started = True
        backend.mechanical = object()
        backend.tree = SimpleNamespace()
        backend.model = SimpleNamespace()
        backend.graphics = SimpleNamespace()

    monkeypatch.setattr(backend, "_connect_workbench_model", reconnect)
    monkeypatch.setattr(
        "ea_node_editor.addons.mechanical.backend.collect_catalogue_rows",
        lambda **kwargs: [_row(
            model_revision=3,
            catalogue_id=kwargs["identity"]["catalogue_id"],
            producer_node_id="save-1",
            producer_port="report",
            producer_path="[0]",
            producer_iteration=0,
            system_key="SYS",
        )],
    )
    identity = {
        key: value
        for key, value in _row(
            model_revision=3,
            catalogue_id="00000000-0000-0000-0000-000000000001",
            producer_node_id="save-1",
            producer_port="report",
            producer_path="[0]",
            producer_iteration=0,
            system_key="SYS",
        ).items()
        if key in {
            "schema_version", "model_revision", "producer_iteration", "catalogue_id",
            "producer_node_id", "producer_port", "producer_path", "run_id", "session_id",
            "document_id", "source_key", "system_key",
        }
    }
    args = {
        "format": format_code,
        "source_path": str(source),
        "destination_path": str(destination),
        "work_path": str(work),
        "stage_path": str(staging.primary),
        "stage_companion": "" if staging.companion is None else str(staging.companion),
        "native_project": str(staging.native_project),
        "verify_path": str(staging.verify_project),
        "snapshot_path": str(staging.root / "w.json"),
        "files": [str(destination), *([str(companion_path(destination, "wbpj"))] if format_code == "wbpj" else [])],
        "overwrite": False,
        "catalogue_identity": identity,
        "view_export_path": str(tmp_path / "views.xml"),
        **(
            {
                "include_results": True,
                "include_user_files": True,
                "include_external_imported_files": True,
            }
            if format_code == "wbpz"
            else {}
        ),
    }
    result = backend.workbench_save(args)
    assert result["status"] == "staged" and result["connection_changed"] is True
    assert result["connection_generation"] == 1
    names = [call[0] for call in workbench.calls]
    assert names.index("stop") < names.index("Exit") < names.index("Save") < names.index("reconnect")
    exit_call = next(call for call in workbench.calls if call[0] == "Exit")
    assert exit_call == ("Exit", "Model", True)
    assert workbench.current == work
    assert backend.systems[0]["system_keys"] == ["SYS", "SYS 1"]
    assert backend.systems[0]["label"] == "Primary ³ ° Ω 漢字 \\ path"
    external = next(system for system in workbench.systems if system.Name == "EXT")
    assert external.calls == 0
    snapshots = json.loads(Path(args["snapshot_path"]).read_text(encoding="utf-8"))[
        "snapshots"
    ]
    for snapshot in snapshots.values():
        assert any(system["user_id"] == "EXT" for system in snapshot["systems"])
        assert all(model["system_user_id"] != "EXT" for model in snapshot["models"])
    if format_code == "wbpz":
        assert next(call for call in workbench.calls if call[0] == "Archive")[1:] == (True, True, True, True)
        assert next(call for call in workbench.calls if call[0] == "Unarchive")[3] is False
    else:
        assert all(call[0] not in {"Archive", "Unarchive"} for call in workbench.calls)


def test_workbench_snapshot_fails_applicable_model_lookup(tmp_path: Path) -> None:
    work = _project(tmp_path / "work.wbpj").resolve()
    staging = create_save_staging(tmp_path / "saved.wbpj", "wbpj")
    workbench = _Workbench(work)
    broken = _System(
        "SYS",
        "Broken Model",
        _Container("Model", workbench.calls, "broken"),
        workbench._files,
    )

    def fail(*, ComponentName: str):
        raise RuntimeError(f"applicable {ComponentName} lookup failed")

    broken.GetContainer = fail
    workbench.systems = [broken]
    raw = workbench.run_script_string(
        "_corex_data="
        + repr({
            "format": "wbpj",
            "work_path": str(work),
            "stage_path": str(staging.primary),
            "stage_companion": str(staging.companion),
            "native_project": str(staging.native_project),
            "verify_path": str(staging.verify_project),
            "system": "SYS",
            "snapshot_path": str(staging.root / "w.json"),
        })
        + "\n"
        + WORKBENCH_SAVE_BODY
    )
    assert raw["ok"] is False
    assert raw["error_type"] == "restore_after_RuntimeError"
    assert len(raw["error_digest"]) == 64


def _write_state(path: Path, **options) -> None:
    import h5py
    import numpy as np

    path.parent.mkdir(parents=True, exist_ok=True)
    userblock_size = options.pop("userblock_size", None)
    root_order = options.pop("root_order", False)
    with h5py.File(path, "w", userblock_size=userblock_size, track_order=root_order) as handle:
        settings = dict(chunks=(262144,), maxshape=(None,), track_times=True)
        settings.update(options)
        dataset = handle.create_dataset("Session", data=np.arange(20965, dtype="uint8"), **settings)
        dataset.attrs["UsedSize"] = np.array([20965], dtype="uint64")


@pytest.fixture(scope="module")
def state_bytes(tmp_path_factory):
    import time

    root = tmp_path_factory.mktemp("workbench-state")
    first, second = root / "first.dat", root / "second.dat"
    _write_state(first)
    time.sleep(1.1)  # Real HDF5 object-time tracking, no byte offsets are patched.
    _write_state(second)
    a, b = first.read_bytes(), second.read_bytes()
    assert len(a) == len(b) and a != b
    return a, b


def _state_evidence(tmp_path: Path, state_bytes):
    work_state, stage_state = (
        tmp_path / f"{stem}_files/dp0/act.dat" for stem in ("w", "p")
    )
    for path, content in zip((work_state, stage_state), state_bytes, strict=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    stage_row = {**_semantic_file("act.dat", stage_state), "registered": True}
    evidence = _semantic_evidence(tmp_path, stage_files=[stage_row], verify_files=[stage_row])
    path, receipt, work, project, verify = evidence
    payload = json.loads(path.read_text(encoding="utf-8"))
    for phase in ("before", "working", "restore"):
        payload["snapshots"][phase]["files"] = [
            {**_semantic_file("act.dat", work_state), "registered": True}
        ]
    _write_state_snapshot(path, receipt, payload)
    args = dict(receipt=receipt, format_code="wbpz", work_path=work,
                native_project=project, stage_path=project, verify_path=verify)
    return path, args, payload, (work_state, stage_state)


def _write_state_snapshot(path, receipt, payload):
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    path.write_bytes(encoded)
    receipt.update(snapshot_bytes=len(encoded), snapshot_sha256=hashlib.sha256(encoded).hexdigest())


@pytest.mark.parametrize("format_code", ["wbpj", "wbpz"])
def test_state_logical_equality_is_only_a_working_to_stage_proof(tmp_path, state_bytes, format_code):
    path, args, payload, states = _state_evidence(tmp_path, state_bytes)
    if format_code == "wbpj":
        args["format_code"] = format_code
        payload["snapshots"]["verify"] = payload["snapshots"]["stage"]
        _write_state_snapshot(path, args["receipt"], payload)
    before = [item.read_bytes() for item in states]
    proof = validate_workbench_semantic_snapshots(path, **args)
    logical = proof["state_file_logical_comparison"]
    assert logical["logical_bytes"] == 20965
    assert logical["working_sha256"] != logical["stage_sha256"]
    assert [item.read_bytes() for item in states] == before
    assert payload["snapshots"]["working"]["files"][0]["sha256"] == logical["working_sha256"]


@pytest.mark.parametrize("phase", ["verify", "restore"])
def test_state_equivalence_never_relaxes_other_phases(tmp_path, state_bytes, monkeypatch, phase):
    import ea_node_editor.addons.mechanical.workbench as module

    path, args, payload, _states = _state_evidence(tmp_path, state_bytes)
    payload["snapshots"][phase]["files"][0]["sha256"] = "0" * 64
    _write_state_snapshot(path, args["receipt"], payload)
    monkeypatch.setattr(module, "_compare_workbench_state", lambda *a: pytest.fail("HDF5 ran before strict checks"))
    with pytest.raises(RuntimeError, match=f"inventory changed during {phase}"):
        validate_workbench_semantic_snapshots(path, **args)


@pytest.mark.parametrize("mismatch", ["another_file", "size", "registered", "display_text", "associations", "wrong_path"])
def test_state_equivalence_requires_the_sole_sha_mismatch(tmp_path, state_bytes, monkeypatch, mismatch):
    import ea_node_editor.addons.mechanical.workbench as module

    path, args, payload, _states = _state_evidence(tmp_path, state_bytes)
    if mismatch == "another_file":
        for phase, snapshot in payload["snapshots"].items():
            row = dict(snapshot["files"][0])
            location = Path(row["location"]).with_name("other.dat")
            row.update(file_name="other.dat", display_text="other.dat", location=str(location),
                       location_key=os.path.normcase(str(location)), sha256=("1" if phase in ("stage", "verify") else "2") * 64)
            snapshot["files"].append(row)
    elif mismatch == "wrong_path":
        for snapshot in payload["snapshots"].values():
            row = snapshot["files"][0]
            location = Path(row["location"]).parent.parent / "act.dat"
            row.update(location=str(location), location_key=os.path.normcase(str(location)))
    else:
        value = {"size": 123, "registered": False, "display_text": "changed", "associations": ["changed"]}[mismatch]
        for phase in ("stage", "verify"):
            payload["snapshots"][phase]["files"][0][mismatch] = value
    _write_state_snapshot(path, args["receipt"], payload)
    monkeypatch.setattr(module, "_compare_workbench_state", lambda *a: pytest.fail("unqualified HDF5 comparison"))
    with pytest.raises(RuntimeError, match="inventory changed during stage"):
        validate_workbench_semantic_snapshots(path, **args)


@pytest.mark.parametrize("presence", ["neither", "working_only", "stage_only", "duplicate", "identical_unknown_schema"])
def test_state_membership_and_byte_proof(tmp_path, state_bytes, monkeypatch, presence):
    import ea_node_editor.addons.mechanical.workbench as module

    pair = (b"unfamiliar but byte-identical",) * 2 if presence == "identical_unknown_schema" else state_bytes
    path, args, payload, _states = _state_evidence(tmp_path, pair)
    if presence == "neither":
        for snapshot in payload["snapshots"].values():
            snapshot["files"] = []
    elif presence in ("working_only", "stage_only"):
        payload["snapshots"]["stage" if presence == "working_only" else "working"]["files"] = []
    elif presence == "duplicate":
        payload["snapshots"]["working"]["files"] *= 2
    _write_state_snapshot(path, args["receipt"], payload)
    monkeypatch.setattr(module, "_compare_workbench_state", lambda *a: pytest.fail("unexpected HDF5 read"))
    if presence in ("neither", "identical_unknown_schema"):
        assert validate_workbench_semantic_snapshots(path, **args)["state_file_logical_comparison"] is None
    else:
        with pytest.raises(RuntimeError, match="membership changed|locations are ambiguous"):
            validate_workbench_semantic_snapshots(path, **args)


@pytest.mark.parametrize("mutation", ["data", "dtype", "shape", "used_size", "attribute_type", "extra_attribute", "root_attribute", "extra_object", "alias", "soft_link", "external_link", "comment", "fillvalue", "maxshape", "chunks", "track_times", "track_order", "root_order", "external_storage", "virtual_storage", "userblock"])
def test_real_state_schema_and_metadata_are_strict(tmp_path, state_bytes, mutation):
    import h5py
    import numpy as np
    from ea_node_editor.addons.mechanical.workbench import _compare_workbench_state

    _path, _args, _payload, paths = _state_evidence(tmp_path, state_bytes)
    right = paths[1]
    if mutation in ("fillvalue", "maxshape", "chunks", "track_times", "track_order", "root_order", "dtype"):
        value = {"fillvalue": 1, "maxshape": (524288,), "chunks": (16384,), "track_times": False,
                 "track_order": True, "root_order": True, "dtype": "uint16"}[mutation]
        _write_state(right, **{mutation: value})
    elif mutation == "userblock":
        for path in paths:
            _write_state(path, userblock_size=512)
    else:
        with h5py.File(right, "r+") as handle:
            dataset = handle["Session"]
            if mutation == "data":
                dataset[0] = 1
            elif mutation == "shape":
                dataset.resize((20964,))
                dataset.attrs.modify("UsedSize", np.array([20964], dtype="uint64"))
            elif mutation == "used_size":
                dataset.attrs.modify("UsedSize", np.array([20964], dtype="uint64"))
            elif mutation == "attribute_type":
                del dataset.attrs["UsedSize"]
                dataset.attrs["UsedSize"] = np.array([20965], dtype="uint32")
            elif mutation == "extra_attribute":
                dataset.attrs["extra"] = 1
            elif mutation == "root_attribute":
                handle.attrs["extra"] = 1
            elif mutation == "extra_object":
                handle.create_group("extra")
            elif mutation == "alias":
                handle["alias"] = dataset
            elif mutation == "external_link":
                del handle["Session"]
                handle["Session"] = h5py.ExternalLink("must-not-be-opened.h5", "data")
            elif mutation == "soft_link":
                del handle["Session"]
                handle["Session"] = h5py.SoftLink("/must-not-be-followed")
            elif mutation == "comment":
                handle["/"].id.set_comment(b"Session", b"changed")
            elif mutation == "external_storage":
                del handle["Session"]
                handle.create_dataset("Session", shape=(20965,), dtype="uint8", external=[("must-not-be-opened.bin", 0, 20965)])
            elif mutation == "virtual_storage":
                del handle["Session"]
                layout = h5py.VirtualLayout(shape=(20965,), dtype="uint8")
                layout[:] = h5py.VirtualSource("must-not-be-opened.h5", "data", shape=(20965,))
                handle.create_virtual_dataset("Session", layout)
    rows = tuple({**_semantic_file("act.dat", path), "registered": True} for path in paths)
    with pytest.raises(RuntimeError, match="state equivalence failed"):
        _compare_workbench_state(paths, rows)


@pytest.mark.parametrize("failure", ["reparse", "path_text", "hash", "bounds", "post_read_change", "io_error"])
def test_state_file_attestation_and_read_failures(tmp_path, state_bytes, monkeypatch, failure):
    import h5py
    import ea_node_editor.addons.mechanical.workbench as module

    _path, _args, _payload, paths = _state_evidence(tmp_path, state_bytes)
    rows = tuple({**_semantic_file("act.dat", path), "registered": True} for path in paths)
    if failure == "reparse":
        monkeypatch.setattr(module, "is_reparse_point", lambda path: path == paths[1].parent)
        monkeypatch.setattr(h5py, "File", lambda *a, **k: pytest.fail("followed a reparse path"))
    elif failure == "path_text":
        rows[0]["location"] = str(paths[0].parent / ".." / "dp0" / "act.dat")
    elif failure == "hash":
        rows[0]["sha256"] = "0" * 64
    elif failure == "bounds":
        monkeypatch.setattr(module, "_STATE_MAX_BYTES", 1024)
    else:
        original = h5py.File

        def read(path, *args, **kwargs):
            if failure == "io_error":
                raise OSError("injected read error")
            if Path(path) == paths[0]:
                with paths[0].open("ab") as stream:
                    stream.write(b"changed")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(h5py, "File", read)
    with pytest.raises(RuntimeError, match="state equivalence failed"):
        module._compare_workbench_state(paths, rows)
