from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
import psutil
import pandas as pd

from ea_node_editor.addons.mechanical.owner_process import (
    MechanicalOwnerProcess,
    OwnerProtocolError,
    _creation_time_for_pid,
    _owner_command,
    _read_bulk,
    _read_search_bulk,
    _validate_search_result,
    _write_search_bulk,
)
from ea_node_editor.addons.mechanical.contracts import (
    encode_selector,
    object_value,
    search_details_table,
)
from ea_node_editor.runtime_contracts import DataTree, RuntimeArtifactRef, RuntimeHandleRef, TypedInlineValue
from ea_node_editor.runtime_contracts.scientific_values import snapshot_scientific_value


def test_real_owner_process_has_exact_identity_and_bounded_protocol() -> None:
    owner = MechanicalOwnerProcess()
    try:
        assert owner.identity.pid != os.getpid()
        assert owner.request(
            run_id="run",
            session_id="session",
            workspace_id="workspace",
            expected_revision=0,
            operation="health",
        ) == {"status": "ready"}
        with pytest.raises(OwnerProtocolError, match="Unsupported"):
            owner.request(
                run_id="run",
                session_id="session",
                workspace_id="workspace",
                expected_revision=0,
                operation="eval",
                args={"code": "1 + 1"},
            )
        with pytest.raises(OwnerProtocolError, match="identity"):
            owner.request(
                run_id="other",
                session_id="session",
                workspace_id="workspace",
                expected_revision=0,
                operation="health",
            )
    finally:
        owner.close()
    assert not owner.alive


def test_owner_protocol_rejects_non_data_arguments() -> None:
    owner = MechanicalOwnerProcess()
    try:
        with pytest.raises(TypeError):
            owner.request(
                run_id="run",
                session_id="session",
                workspace_id="workspace",
                expected_revision=0,
                operation="health",
                args={"value": object()},
            )
    finally:
        owner.close()


def test_owner_protocol_survives_handshake_timeout_while_idle() -> None:
    owner = MechanicalOwnerProcess()
    try:
        request = dict(
            run_id="run",
            session_id="session",
            workspace_id="workspace",
            expected_revision=0,
            operation="health",
        )
        assert owner.request(**request) == {"status": "ready"}
        time.sleep(10.1)
        assert owner.request(**request) == {"status": "ready"}
    finally:
        owner.close()


def test_owner_commands_use_module_in_source_and_private_role_when_frozen(monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert _owner_command() == [sys.executable, "-m", "ea_node_editor.addons.mechanical.owner_process"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert _owner_command() == [sys.executable, "--private-mechanical-owner"]


def test_bulk_reader_rejects_escape_and_deletes_bad_hash(tmp_path: Path) -> None:
    with pytest.raises(OwnerProtocolError, match="kind/path"):
        _read_bulk(tmp_path, {"kind": "scientific", "relative_name": "../x", "byte_length": 0, "sha256": "0" * 64})
    payload = tmp_path / "catalogue-test.json"
    payload.write_bytes(b"{}")
    with pytest.raises(OwnerProtocolError, match="hash"):
        _read_bulk(tmp_path, {"kind": "scientific", "relative_name": payload.name, "byte_length": 2, "sha256": "0" * 64})
    assert not payload.exists()


def _search_identity():
    return {
        "run_id": "run", "session_id": "session", "document_id": "document",
        "source_key": "source", "system_key": "system", "model_revision": 0,
    }


def _search_object(index: int, *, name: str = "Object"):
    identity = _search_identity()
    path = f"Model/{index}"
    return object_value({
        **identity, "object_id": index, "parent_id": None, "object_path": path,
        "display_name": name, "api_type": "Native.Type", "category": "Type",
        "analysis_id": None,
        "selector_code": encode_selector(
            "object", document_id=identity["document_id"], system_key=identity["system_key"],
            object_path=path, native_id=index,
        ),
    })


def test_search_spool_roundtrips_above_control_envelope_and_deletes_eagerly(tmp_path: Path) -> None:
    result = {
        "objects": [_search_object(index, name="x" * 600) for index in range(2_000)],
        "properties": [],
        "details": search_details_table([]),
    }
    descriptor = _write_search_bulk(tmp_path, result, _search_identity())
    assert descriptor["kind"] == "mechanical-search-v1"
    assert descriptor["byte_length"] > 1024 * 1024
    path = tmp_path / descriptor["relative_name"]
    restored = _read_search_bulk(tmp_path, descriptor, _search_identity())
    assert len(restored["objects"]) == 2_000
    assert not path.exists()


def test_search_spool_rejects_extra_wrong_identity_and_live_carriers() -> None:
    details = search_details_table([])
    with pytest.raises(OwnerProtocolError, match="schema"):
        _validate_search_result({"objects": [], "properties": [], "details": details, "extra": 1})
    with pytest.raises(OwnerProtocolError, match="identity"):
        _validate_search_result({"objects": [_search_object(1)], "properties": [], "details": details}, {**_search_identity(), "run_id": "other"})
    handle = RuntimeHandleRef(
        data_type_id="COREX.Mechanical.Model", schema_version=1, handle_id="h",
        kind="mechanical.model", owner_scope="run", worker_generation=1, metadata={},
    )
    with pytest.raises(OwnerProtocolError, match="live references"):
        _validate_search_result({"objects": [handle], "properties": [], "details": details})
    artifact = RuntimeArtifactRef.staged(
        "artifact", data_type_id="COREX.DataTypes.Path", schema_version=1,
        format="file", size_bytes=0, sha256="0" * 64, provenance="test",
    )
    for bad in (
        artifact,
        DataTree.from_item(_search_object(1)),
        TypedInlineValue("COREX.Mechanical.Property", 1, {}),
    ):
        with pytest.raises(OwnerProtocolError):
            _validate_search_result({"objects": [bad], "properties": [], "details": details})
    with pytest.raises(OwnerProtocolError, match="carriers"):
        _validate_search_result({
            "objects": [_search_object(1)] * 100_001,
            "properties": [], "details": details,
        })
    with pytest.raises(OwnerProtocolError, match="carriers"):
        _validate_search_result({
            "objects": [], "properties": [],
            "details": snapshot_scientific_value(pd.DataFrame({"wrong": [1]})),
        })


def test_owner_cleanup_removes_orphan_search_spool(tmp_path: Path) -> None:
    owner = MechanicalOwnerProcess(work_root=tmp_path)
    orphan = tmp_path / "search-orphan.json"
    orphan.write_text("{}", encoding="utf-8")
    owner.close()
    assert not orphan.exists()


def test_owner_transport_crash_is_detected_without_touching_other_processes() -> None:
    owner = MechanicalOwnerProcess()
    pid = owner.identity.pid
    process = psutil.Process(pid)
    process.kill()
    process.wait(timeout=2.0)
    with pytest.raises(OwnerProtocolError, match="closed"):
        owner.request(
            run_id="run",
            session_id="session",
            workspace_id="workspace",
            expected_revision=0,
            operation="health",
            timeout_sec=0.1,
        )
    assert owner.identity.pid == pid and not owner.alive
    owner.close()


def _wait_for_identity(path: Path) -> dict:
    deadline = time.monotonic() + 10.0
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    return json.loads(path.read_text(encoding="utf-8"))


def _wait_owned_identity_dead(identity: dict) -> None:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            if _creation_time_for_pid(identity["pid"]) != identity["creation_time_ns"]:
                return
        except OSError:
            return
        time.sleep(0.02)
    pytest.fail(f"owned process identity survived: {identity}")


def test_missed_explicit_shutdown_does_not_orphan_owner(tmp_path: Path) -> None:
    identity_path = tmp_path / "owner.json"
    script = (
        "import json,os,sys; "
        "from ea_node_editor.addons.mechanical.owner_process import MechanicalOwnerProcess; "
        "o=MechanicalOwnerProcess(); "
        "open(sys.argv[1],'w').write(json.dumps({'pid':o.identity.pid,'creation_time_ns':o.identity.creation_time_ns})); "
        "os._exit(0)"
    )
    parent = subprocess.Popen([sys.executable, "-c", script, str(identity_path)])
    identity = _wait_for_identity(identity_path)
    parent.wait(timeout=10.0)
    _wait_owned_identity_dead(identity)


def test_forced_parent_death_does_not_orphan_owner(tmp_path: Path) -> None:
    identity_path = tmp_path / "owner.json"
    script = (
        "import json,sys,time; "
        "from ea_node_editor.addons.mechanical.owner_process import MechanicalOwnerProcess; "
        "o=MechanicalOwnerProcess(); "
        "open(sys.argv[1],'w').write(json.dumps({'pid':o.identity.pid,'creation_time_ns':o.identity.creation_time_ns})); "
        "time.sleep(60)"
    )
    parent = subprocess.Popen([sys.executable, "-c", script, str(identity_path)])
    identity = _wait_for_identity(identity_path)
    parent_process = psutil.Process(parent.pid)
    parent_process.kill()
    parent_process.wait(timeout=5.0)
    _wait_owned_identity_dead(identity)
