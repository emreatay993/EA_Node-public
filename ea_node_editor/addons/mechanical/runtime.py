# Purpose: Execute Mechanical Open, read, graphics, mutation, and save operations through the run-owned session.
# Map: subsystems/addons.md
# Tests: tests/mechanical_catalogue/test_open_model.py, tests/mechanical_catalogue/test_search_tree.py, tests/mechanical_catalogue/test_result_tables.py, tests/mechanical_catalogue/test_image_export.py, tests/mechanical_catalogue/test_scripts.py, tests/mechanical_catalogue/test_snippets.py, tests/mechanical_catalogue/test_standalone_save.py, tests/mechanical_catalogue/test_workbench_save.py, tests/mechanical_catalogue/test_workbench_model_export.py
# Landmarks: execute_open_model; execute_run_script; execute_apdl_snippet; execute_save_model; execute_image_export

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from ea_node_editor.addons.mechanical.contracts import (
    CAMERA_VIEW_TYPE_ID,
    OBJECT_TYPE_ID,
    PROPERTY_TYPE_ID,
    decode_selector,
    validate_camera_view,
    validate_object,
    validate_property,
)
from ea_node_editor.addons.mechanical.commands import snippet_object_values
from ea_node_editor.addons.mechanical.graphics import (
    CAMERA_IDENTITY_FIELDS,
    IMAGE_CAPTURE_LIMIT,
    IMAGE_MAX_PIXELS,
    build_image_outputs,
    preflight_image_destinations,
    publish_image_batch,
    render_image_filenames,
)
from ea_node_editor.addons.mechanical.session import StaleMechanicalModelError
from ea_node_editor.addons.mechanical.saving import (
    create_save_staging,
    preflight_save_destination,
    publish_save,
    resolve_save_format,
    validate_model_export_save_receipt,
    validate_native_save_receipt,
    validate_staged_bundle,
)
from ea_node_editor.addons.mechanical.workbench import validate_workbench_save_receipt
from ea_node_editor.addons.mechanical.owner_process import (
    MechanicalOwnerProcess,
    OwnerProtocolError,
)
from ea_node_editor.nodes.execution_context import NodeInputNotReadyError
from ea_node_editor.runtime_contracts import (
    ImageValue,
    RuntimeHandleRef,
    TableValue,
    TypedInlineValue,
    serialize_runtime_value,
)


def discover_mechanical_releases() -> tuple[int, ...]:
    try:
        from ansys.tools.common.path import get_available_ansys_installations
        found = get_available_ansys_installations()
    except (ImportError, OSError) as exc:
        raise RuntimeError("Mechanical installation discovery is unavailable") from exc
    releases = tuple(sorted((int(code) for code in found if int(code) >= 261), reverse=True))
    return releases


def _release(requested: object) -> int:
    if isinstance(requested, bool) or not isinstance(requested, (int, float)) or int(requested) != requested:
        raise ValueError("Version must be an integer release code")
    code = int(requested)
    if code and code < 261:
        raise ValueError("mechanical.release_unsupported: releases earlier than 261 are unsupported")
    available = discover_mechanical_releases()
    if not available:
        raise RuntimeError("mechanical.release_unsupported: no supported Mechanical release (261 or newer) is installed")
    if code and code not in available:
        raise RuntimeError(f"mechanical.release_unsupported: release {code} is not installed; available releases: {list(available)}")
    return code or available[0]


def _source_key(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _setting(ctx, settings, key: str, default):
    if key in ctx.inputs:
        return ctx.inputs[key]
    if settings is not None and hasattr(settings, key):
        return getattr(settings, key)
    return ctx.properties.get(key, default)


def execute_open_model(ctx, settings=None):
    raw_source = _setting(ctx, settings, "file", "")
    if not str(raw_source or "").strip():
        raise NodeInputNotReadyError("File requires an existing Mechanical model or archive")
    source = ctx.resolve_path_value(raw_source)
    if source is None or not source.is_file():
        raise ValueError(f"mechanical.open_failed: File must resolve to an existing regular file: {raw_source}")
    suffix = source.suffix.casefold()
    if suffix not in {".mechdat", ".mechdb", ".mechpz", ".wbpj", ".wbpz"}:
        raise ValueError("File must be .mechdat, .mechdb, .mechpz, .wbpj, or .wbpz")
    mode = str(_setting(ctx, settings, "mode", "background")).strip()
    if mode not in {"background", "interactive"}:
        raise ValueError("Mode must be background or interactive")
    timeout = float(_setting(ctx, settings, "timeout_s", 600.0))
    if not 1 <= timeout <= 86400:
        raise ValueError("Timeout must be between 1 and 86400 seconds")
    release = _release(_setting(ctx, settings, "version", 0))
    working_value = _setting(ctx, settings, "working_folder", "")
    working = ctx.resolve_path_value(working_value) if str(working_value or "").strip() else None
    system = str(_setting(ctx, settings, "system", "") or "").strip()
    catalogue_id = str(uuid4())
    source_key = _source_key(source)
    document_id = str(
        uuid5(
            NAMESPACE_URL,
            f"corex-mechanical:{os.path.normcase(str(source.resolve()))}:{source_key}",
        )
    )
    if system.startswith("{"):
        selector = decode_selector(system)
        if (
            selector["kind"] != "system"
            or selector["document_id"] != document_id
            or selector["object_path"]
            or type(selector["native_id"]) is not str
            or selector["system_key"] != selector["native_id"]
        ):
            raise ValueError("mechanical.open_failed: system selector belongs to another source or kind")
        system = selector["native_id"]
    session = ctx.mechanical_sessions.open_session(
        run_id=ctx.run_id, workspace_id=ctx.workspace_id, open_node_id=ctx.node_id,
        source_path=source, target_path=ctx.target_path,
        target_iteration=ctx.target_iteration, backend_mode=mode,
        working_folder=working, register_cancel=ctx.register_cancel,
    )
    identity = {
        "schema_version": 1, "model_revision": 0,
        "producer_iteration": ctx.target_iteration, "catalogue_id": catalogue_id,
        "producer_node_id": ctx.node_id, "producer_port": "info",
        "producer_path": json.dumps(list(ctx.target_path), separators=(",", ":")),
        "run_id": ctx.run_id, "session_id": session.session_id,
        "document_id": document_id, "source_key": source_key,
        "system_key": system,
    }
    try:
        result = ctx.mechanical_sessions.operate(
            session, expected_revision=0, operation="open", timeout_sec=timeout,
            args={
                "source_path": str(source), "work_path": str(session.work_path),
                "mode": mode, "release_code": release, "system": system,
                "timeout_sec": timeout,
                "catalogue_identity": identity,
                "view_export_path": str(session.work_root / "catalogue-views.xml"),
            },
        )
    except TimeoutError as exc:
        raise TimeoutError(
            f"mechanical.operation_timeout: source={source}; release={release}; {exc}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"mechanical.open_failed: source={source}; release={release}; {exc}"
        ) from exc
    outputs = {"info": result["catalogue"]}
    if result["status"] == "system_required":
        ctx.warn("Select a Mechanical Model/system and run again.", code="mechanical.system_required")
        return outputs
    selected = str(result["system_key"])
    outputs["model"] = ctx.mechanical_sessions.register_model(
        session, document_id=document_id, source_key=source_key,
        system_key=selected, release_code=release, catalogue_id=catalogue_id,
    )
    return outputs


def _script_environment(
    value: object, metadata: Mapping[str, Any], *, operation: str = "Run Mechanical Script"
) -> dict[str, Any]:
    if type(value) is TypedInlineValue:
        if value.data_type_id != OBJECT_TYPE_ID or not validate_object(value):
            raise TypeError(f"{operation} Environments accepts Mechanical Object or Text values")
        identity_fields = (
            "run_id", "session_id", "document_id", "source_key", "system_key", "model_revision"
        )
        if any(value.payload[field] != metadata[field] for field in identity_fields):
            raise ValueError("mechanical.cross_session_reference: Environment belongs to another Model")
        if value.payload["analysis_id"] != value.payload["object_id"]:
            raise ValueError(f"{operation} Environment must identify an analysis tree object")
        return {
            "kind": "typed",
            "object_id": value.payload["object_id"],
            "object_path": value.payload["object_path"],
        }
    if type(value) is not str or not value.strip():
        raise TypeError(f"{operation} Environments must contain non-empty Object or Text values")
    text = value.strip()
    if text.startswith("{"):
        selector = decode_selector(text)
        if (
            selector["kind"] != "object"
            or selector["document_id"] != metadata["document_id"]
            or selector["system_key"] != metadata["system_key"]
            or type(selector["native_id"]) is not int
            or not selector["object_path"]
        ):
            raise ValueError("mechanical.selector_missing: Environment selector belongs to another model or kind")
        return {
            "kind": "typed",
            "object_id": selector["native_id"],
            "object_path": selector["object_path"],
        }
    return {"kind": "text", "text": text}


def _execute_model_mutation(
    ctx,
    session,
    metadata: Mapping[str, Any],
    *,
    expected_revision: int,
    operation: str,
    args: Mapping[str, Any],
    timeout_sec: float,
    label: str,
    connection_change: bool = False,
) -> dict[str, Any]:
    response = None
    operation_error: BaseException | None = None
    try:
        response = ctx.mechanical_sessions.operate(
            session,
            expected_revision=expected_revision,
            operation=operation,
            mutation=True,
            connection_change=connection_change,
            timeout_sec=timeout_sec,
            args=args,
        )
    except StaleMechanicalModelError as exc:
        raise ValueError(f"mechanical.stale_reference: {exc}") from exc
    except BaseException as exc:
        operation_error = exc
    invalidation_error: BaseException | None = None
    try:
        ctx.request_observation_invalidation(
            str(metadata["producer_node_id"]),
            reason_code="mechanical_model_mutated",
        )
    except BaseException as exc:
        invalidation_error = exc
    if isinstance(operation_error, (TimeoutError, OwnerProtocolError)):
        retirement_error: BaseException | None = None
        try:
            ctx.mechanical_sessions.retire_session(session)
        except Exception as close_exc:
            retirement_error = close_exc
        detail = str(operation_error)
        if invalidation_error is not None:
            detail += f"; observation invalidation failed: {invalidation_error}"
        if retirement_error is not None:
            detail += f"; session retirement failed: {retirement_error}"
        raise RuntimeError(f"mechanical.operation_uncertain: {detail}") from operation_error
    if operation_error is not None:
        detail = str(operation_error)
        if invalidation_error is not None:
            detail += f"; observation invalidation failed: {invalidation_error}"
        raise RuntimeError(f"mechanical.operation_failed: {label}: {detail}") from operation_error
    if invalidation_error is not None:
        raise RuntimeError(
            f"mechanical.operation_failed: observation invalidation failed: {invalidation_error}"
        ) from invalidation_error
    assert isinstance(response, dict)
    return response


def execute_run_script(ctx, model=None, environments=None, settings=None):
    if model is None:
        raise NodeInputNotReadyError("Model requires a live Mechanical model from this run")
    if not isinstance(model, RuntimeHandleRef):
        raise TypeError("Run Mechanical Script requires a Mechanical Model")
    try:
        session = ctx.mechanical_sessions.admit_model(
            model, run_id=ctx.run_id, workspace_id=ctx.workspace_id
        )
    except StaleMechanicalModelError as exc:
        raise ValueError(f"mechanical.stale_reference: {exc}") from exc
    metadata = model.metadata
    raw_environments = [] if environments is None else environments
    if type(raw_environments) not in {list, tuple}:
        raise TypeError("Run Mechanical Script Environments must be a list")
    selectors = [_script_environment(value, metadata) for value in raw_environments]
    scope = _setting(ctx, settings, "scope", "each_environment")
    if scope not in {"each_environment", "model_once"}:
        raise ValueError("Run Mechanical Script Scope must be each_environment or model_once")
    code = _setting(ctx, settings, "code", "")
    if type(code) is not str or not code.strip():
        raise NodeInputNotReadyError("Code requires a non-empty Mechanical IronPython script")
    timeout = _setting(ctx, settings, "timeout_s", 600.0)
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(float(timeout))
        or not 1 <= float(timeout) <= 86400
    ):
        raise ValueError("Timeout must be a finite number between 1 and 86400 seconds")
    stop_on_error = _setting(ctx, settings, "stop_on_error", True)
    if type(stop_on_error) is not bool:
        raise TypeError("Run Mechanical Script Stop on error must be Boolean")
    expected_revision = metadata["model_revision"]
    try:
        preflight = ctx.mechanical_sessions.operate(
            session,
            expected_revision=expected_revision,
            operation="script_preflight",
            args={"environments": selectors, "scope": scope},
            timeout_sec=float(timeout),
        )["script_preflight"]
    except StaleMechanicalModelError as exc:
        raise ValueError(f"mechanical.stale_reference: {exc}") from exc
    except Exception as exc:
        message = str(exc)
        for code_name in (
            "mechanical.selector_ambiguous:",
            "mechanical.selector_missing:",
            "mechanical.capacity_exceeded:",
        ):
            if code_name in message:
                raise ValueError(message[message.index(code_name):]) from exc
        raise RuntimeError(f"mechanical.operation_failed: Script preflight: {message}") from exc
    catalogue_id = str(uuid4())
    new_revision = expected_revision + 1
    identity = {
        "schema_version": 1,
        "model_revision": new_revision,
        "producer_iteration": ctx.target_iteration,
        "catalogue_id": catalogue_id,
        "producer_node_id": ctx.node_id,
        "producer_port": "report",
        "producer_path": json.dumps(list(ctx.target_path), separators=(",", ":")),
        "run_id": ctx.run_id,
        "session_id": metadata["session_id"],
        "document_id": metadata["document_id"],
        "source_key": metadata["source_key"],
        "system_key": metadata["system_key"],
    }
    response = _execute_model_mutation(
        ctx,
        session,
        metadata,
        expected_revision=expected_revision,
        operation="run_script",
        timeout_sec=float(timeout),
        label="Run Mechanical Script",
        args={
            "selected_ids": list(preflight["selected_ids"]),
            "scope": scope,
            "code": code,
            "stop_on_error": stop_on_error,
            "catalogue_identity": identity,
            "view_export_path": str(session.work_root / f"script-views-{uuid4().hex}.xml"),
        },
    )
    script_result = response.get("script")
    if response.get("status") != "executed":
        detail = json.dumps(script_result, ensure_ascii=False, separators=(",", ":"))
        raise ValueError(f"mechanical.script_failed: {detail}")
    if session.revision != new_revision or type(response.get("catalogue")) is not TableValue:
        raise RuntimeError("mechanical.operation_failed: Script revision or Report catalogue is invalid")
    return {
        "model": ctx.mechanical_sessions.register_model(
            session,
            document_id=metadata["document_id"],
            source_key=metadata["source_key"],
            system_key=metadata["system_key"],
            release_code=metadata["release_code"],
            catalogue_id=catalogue_id,
            producer_node_id=ctx.node_id,
            producer_port="report",
            producer_path=ctx.target_path,
            producer_iteration=ctx.target_iteration,
        ),
        "report": response["catalogue"],
    }


def execute_apdl_snippet(ctx, model=None, environments=None, settings=None):
    if model is None:
        raise NodeInputNotReadyError("Model requires a live Mechanical model from this run")
    if not isinstance(model, RuntimeHandleRef):
        raise TypeError("Mechanical APDL Snippet requires a Mechanical Model")
    try:
        session = ctx.mechanical_sessions.admit_model(
            model, run_id=ctx.run_id, workspace_id=ctx.workspace_id
        )
    except StaleMechanicalModelError as exc:
        raise ValueError(f"mechanical.stale_reference: {exc}") from exc
    metadata = model.metadata
    raw_environments = [] if environments is None else environments
    if type(raw_environments) not in {list, tuple}:
        raise TypeError("Mechanical APDL Snippet Environments must be a list")
    selectors = [
        _script_environment(value, metadata, operation="Mechanical APDL Snippet")
        for value in raw_environments
    ]
    name = _setting(ctx, settings, "name", "COREX commands")
    if type(name) is not str or not name.strip():
        raise NodeInputNotReadyError("Name requires non-empty text")
    commands = _setting(ctx, settings, "commands", "")
    if type(commands) is not str or not commands.strip():
        raise NodeInputNotReadyError("Commands requires non-empty APDL text")
    steps = _setting(ctx, settings, "steps", "all")
    if steps not in {"all", "selected"}:
        raise ValueError("Steps must be all or selected")
    selected_steps: list[int] = []
    if steps == "selected":
        raw_steps = _setting(ctx, settings, "selected_steps", [1])
        if type(raw_steps) not in {list, tuple} or not raw_steps:
            raise ValueError("Selected load steps requires a non-empty Integer List")
        if any(type(step) is not int or step < 1 for step in raw_steps):
            raise ValueError("Selected load steps must contain positive integers")
        selected_steps = list(raw_steps)
        if len(selected_steps) != len(set(selected_steps)):
            raise ValueError("Selected load steps must be unique")
    issue_solve = _setting(ctx, settings, "issue_solve_command", False)
    if type(issue_solve) is not bool:
        raise TypeError("Issue SOLVE command must be Boolean")
    node_token = hashlib.sha256(str(ctx.node_id).encode("utf-8")).hexdigest()[:32]
    expected_revision = metadata["model_revision"]
    preflight_args = {
        "environments": selectors,
        "name": name,
        "steps": steps,
        "selected_steps": selected_steps,
        "owner_node_token": node_token,
    }
    try:
        preflight = ctx.mechanical_sessions.operate(
            session,
            expected_revision=expected_revision,
            operation="snippet_preflight",
            args=preflight_args,
            timeout_sec=600.0,
        )["snippet_preflight"]
    except StaleMechanicalModelError as exc:
        raise ValueError(f"mechanical.stale_reference: {exc}") from exc
    except Exception as exc:
        message = str(exc)
        for code_name in (
            "mechanical.selector_ambiguous:",
            "mechanical.selector_missing:",
            "mechanical.capacity_exceeded:",
            "mechanical.capability_unproved:",
            "mechanical.operation_failed:",
        ):
            if code_name in message:
                raise ValueError(message[message.index(code_name):]) from exc
        raise RuntimeError(f"mechanical.operation_failed: Snippet preflight: {message}") from exc
    catalogue_id = str(uuid4())
    new_revision = expected_revision + 1
    identity = {
        "schema_version": 1,
        "model_revision": new_revision,
        "producer_iteration": ctx.target_iteration,
        "catalogue_id": catalogue_id,
        "producer_node_id": ctx.node_id,
        "producer_port": "report",
        "producer_path": json.dumps(list(ctx.target_path), separators=(",", ":")),
        "run_id": ctx.run_id,
        "session_id": metadata["session_id"],
        "document_id": metadata["document_id"],
        "source_key": metadata["source_key"],
        "system_key": metadata["system_key"],
    }
    response = _execute_model_mutation(
        ctx,
        session,
        metadata,
        expected_revision=expected_revision,
        operation="run_snippet",
        timeout_sec=600.0,
        label="Mechanical APDL Snippet",
        args={
            "plan": preflight,
            "owner_node_token": node_token,
            "name": name,
            "steps": steps,
            "selected_steps": selected_steps,
            "commands": commands,
            "issue_solve_command": issue_solve,
            "catalogue_identity": identity,
            "view_export_path": str(session.work_root / f"snippet-views-{uuid4().hex}.xml"),
            "rollback_path": str(session.work_root / f"snippet-rollback-{uuid4().hex}.json"),
        },
    )
    snippet_result = response.get("snippet")
    if response.get("status") != "executed":
        detail = json.dumps(snippet_result, ensure_ascii=False, separators=(",", ":"))
        raise ValueError(f"mechanical.snippet_failed: {detail}")
    if session.revision != new_revision or type(response.get("catalogue")) is not TableValue:
        raise RuntimeError("mechanical.operation_failed: Snippet revision or Report catalogue is invalid")
    if not isinstance(snippet_result, Mapping):
        raise RuntimeError("mechanical.operation_failed: Snippet receipt is invalid")
    snippets = snippet_object_values(snippet_result["snippets"], identity)
    return {
        "model": ctx.mechanical_sessions.register_model(
            session,
            document_id=metadata["document_id"],
            source_key=metadata["source_key"],
            system_key=metadata["system_key"],
            release_code=metadata["release_code"],
            catalogue_id=catalogue_id,
            producer_node_id=ctx.node_id,
            producer_port="report",
            producer_path=ctx.target_path,
            producer_iteration=ctx.target_iteration,
        ),
        "snippets": snippets,
        "report": response["catalogue"],
    }


def execute_save_model(ctx, model=None, settings=None):
    if model is None:
        raise NodeInputNotReadyError("Model requires a live Mechanical model from this run")
    if not isinstance(model, RuntimeHandleRef):
        raise TypeError("Save Mechanical Model requires a Mechanical Model")
    try:
        session = ctx.mechanical_sessions.admit_model(
            model, run_id=ctx.run_id, workspace_id=ctx.workspace_id
        )
    except StaleMechanicalModelError as exc:
        raise ValueError(f"mechanical.stale_reference: {exc}") from exc
    metadata = model.metadata
    source = session.source_path.resolve(strict=True)
    raw_destination = _setting(ctx, settings, "file", "")
    if not str(raw_destination or "").strip():
        raise NodeInputNotReadyError("File requires an explicit save destination")
    destination_value = ctx.resolve_path_value(raw_destination)
    if destination_value is None:
        raise ValueError("mechanical.save_failed: File did not resolve to a destination path")
    destination = Path(destination_value).resolve(strict=False)
    source_suffix = source.suffix.casefold()
    format_code = resolve_save_format(
        destination, _setting(ctx, settings, "format", "auto")
    )
    workbench_source = source_suffix in {".wbpj", ".wbpz"}
    workbench_project_save = workbench_source and format_code in {"wbpj", "wbpz"}
    workbench_model_export = workbench_source and format_code in {"mechdb", "mechdat"}
    if workbench_source:
        if format_code == "mechpz":
            raise ValueError(
                "mechanical.save_failed: .mechpz is never valid for a Workbench source; "
                "choose native whole-project .wbpz"
            )
        if not workbench_project_save and not workbench_model_export:
            raise ValueError("mechanical.save_failed: Workbench save format is unsupported")
    elif format_code in {"wbpj", "wbpz"}:
        raise ValueError("mechanical.save_failed: Workbench formats require a Workbench source")
    overwrite = _setting(ctx, settings, "overwrite", False)
    if type(overwrite) is not bool:
        raise TypeError("Overwrite existing must be Boolean")
    if not workbench_source and source_suffix not in {".mechdb", ".mechdat", ".mechpz"}:
        raise ValueError("mechanical.save_failed: Model source is not standalone Mechanical")
    preflight = preflight_save_destination(
        destination,
        source=source,
        format_code=format_code,
        overwrite=overwrite,
    )
    destination = preflight.destination
    destination_companion = preflight.companion
    archive_inputs: dict[str, bool] = {}
    archive_keys = (
        ("include_results", "include_user_files", "include_external_imported_files")
        if format_code == "wbpz"
        else ("include_results", "include_user_files") if format_code == "mechpz" else ()
    )
    for key in archive_keys:
        value = _setting(ctx, settings, key, True)
        if type(value) is not bool:
            raise TypeError(f"{key} must be Boolean")
        archive_inputs[key] = value
    staging = create_save_staging(destination, format_code)
    expected_files = [destination, *([destination_companion] if destination_companion else [])]
    catalogue_id = str(uuid4())
    expected_revision = metadata["model_revision"]
    new_revision = expected_revision + 1
    identity = {
        "schema_version": 1,
        "model_revision": new_revision,
        "producer_iteration": ctx.target_iteration,
        "catalogue_id": catalogue_id,
        "producer_node_id": ctx.node_id,
        "producer_port": "report",
        "producer_path": json.dumps(list(ctx.target_path), separators=(",", ":")),
        "run_id": ctx.run_id,
        "session_id": metadata["session_id"],
        "document_id": metadata["document_id"],
        "source_key": metadata["source_key"],
        "system_key": metadata["system_key"],
    }
    args = {
        "format": format_code,
        "source_path": str(source),
        "destination_path": str(destination),
        "work_path": str(session.work_path),
        "stage_path": str(staging.primary),
        "stage_companion": "" if staging.companion is None else str(staging.companion),
        **(
            {
                "native_project": str(staging.native_project),
                "snapshot_path": str(staging.root / "w.json"),
            }
            if workbench_project_save
            else {
                "bridge_path": str(staging.root / "b" / "b.dsdb"),
                "snapshot_path": str(staging.root / "w.json"),
                "model_snapshot_path": str(staging.root / "m.json"),
            }
            if workbench_model_export
            else {}
        ),
        "verify_path": str(staging.verify_project),
        "files": [str(path) for path in expected_files],
        "overwrite": overwrite,
        "catalogue_identity": identity,
        "view_export_path": str(session.work_root / f"save-views-{uuid4().hex}.xml"),
        **archive_inputs,
    }
    try:
        response = _execute_model_mutation(
            ctx,
            session,
            metadata,
            expected_revision=expected_revision,
            operation=(
                "workbench_save"
                if workbench_project_save
                else "workbench_model_export"
                if workbench_model_export
                else "standalone_save"
            ),
            timeout_sec=600.0,
            label="Save Mechanical Model",
            args=args,
            connection_change=workbench_source,
        )
        if workbench_model_export:
            exported = response.get("native_export")
            if (
                not isinstance(exported, Mapping)
                or set(exported)
                != {"bridge_bytes", "bridge_sha256", "snapshot_bytes", "snapshot_sha256"}
            ):
                raise RuntimeError(
                    "mechanical.save_failed: Workbench export receipt is invalid"
                )
            conversion_owner = MechanicalOwnerProcess(
                work_root=staging.root / "conversion-owner"
            )
            ctx.register_cancel(conversion_owner.close)
            try:
                if ctx.should_stop():
                    raise RuntimeError("mechanical.operation_failed: selected-model conversion cancelled")
                converted = conversion_owner.request(
                    run_id=ctx.run_id,
                    session_id=uuid4().hex,
                    workspace_id=ctx.workspace_id,
                    expected_revision=0,
                    operation="convert_workbench_model",
                    timeout_sec=600.0,
                    args={
                        "format": format_code,
                        "release_code": metadata["release_code"],
                        "bridge_path": args["bridge_path"],
                        "bridge_bytes": exported["bridge_bytes"],
                        "bridge_sha256": exported["bridge_sha256"],
                        "stage_path": args["stage_path"],
                        "stage_companion": args["stage_companion"],
                        "verify_path": args["verify_path"],
                        "model_snapshot_path": args["model_snapshot_path"],
                        "model_snapshot_bytes": exported["snapshot_bytes"],
                        "model_snapshot_sha256": exported["snapshot_sha256"],
                    },
                )
            finally:
                conversion_owner.close()
            if ctx.should_stop():
                raise RuntimeError("mechanical.operation_failed: selected-model conversion cancelled")
            response = {
                **response,
                "status": "staged",
                "native_save": converted.get("native_save"),
            }
    except BaseException as exc:
        if staging.root.exists() and any(path.is_file() for path in staging.root.rglob("*")):
            raise RuntimeError(
                f"mechanical.save_failed: native save failed; recovery_path={staging.root}; {exc}"
            ) from exc
        shutil.rmtree(staging.root, ignore_errors=True)
        raise
    try:
        if response.get("status") != "staged":
            raise RuntimeError("Mechanical save did not return a staged result")
        if workbench_project_save:
            native_receipt = response.get("native_save")
            validate_workbench_save_receipt(
                native_receipt,
                format_code=format_code,
            )
            validate_staged_bundle(staging, format_code=format_code)
        elif workbench_model_export:
            validate_model_export_save_receipt(
                response.get("native_save"),
                format_code=format_code,
                staging=staging,
            )
        else:
            validate_native_save_receipt(
                response.get("native_save"),
                format_code=format_code,
                staging=staging,
            )
        if workbench_source and (
            response.get("connection_changed") is not True
            or response.get("connection_generation") != session.connection_generation
        ):
            raise RuntimeError("Mechanical Workbench reconnect identity is invalid")
        report = response.get("catalogue")
        if session.revision != new_revision or type(report) is not TableValue:
            raise RuntimeError("Mechanical save revision or Report catalogue is invalid")
        if ctx.should_stop():
            raise RuntimeError("mechanical.operation_failed: Save cancelled before publication")
        publication = publish_save(
            staging,
            preflight=preflight,
            format_code=format_code,
        )
    except BaseException as exc:
        if staging.root.exists() and any(path.is_file() for path in staging.root.rglob("*")):
            if "mechanical.publication_recovery_required:" in str(exc):
                raise
            raise RuntimeError(
                f"mechanical.save_failed: staged recovery retained at {staging.root}; {exc}"
            ) from exc
        shutil.rmtree(staging.root, ignore_errors=True)
        raise
    try:
        if publication.files != expected_files or not all(
            path.exists() for path in publication.files
        ):
            raise RuntimeError("mechanical.save_failed: published files are incomplete")
        refreshed_model = ctx.mechanical_sessions.register_model(
            session,
            document_id=metadata["document_id"],
            source_key=metadata["source_key"],
            system_key=metadata["system_key"],
            release_code=metadata["release_code"],
            catalogue_id=catalogue_id,
            producer_node_id=ctx.node_id,
            producer_port="report",
            producer_path=ctx.target_path,
            producer_iteration=ctx.target_iteration,
        )
        outputs = {
            "model": refreshed_model,
            "files": [str(path) for path in publication.files],
            "report": report,
        }
        serialize_runtime_value(outputs, catalog=ctx.worker_services.data_types)
        publication.commit()
        return outputs
    except BaseException as exc:
        try:
            publication.rollback()
        except RuntimeError as restore_exc:
            raise restore_exc from exc
        raise


def _search_selector(query: str, metadata) -> dict[str, object] | None:
    try:
        decoded = json.loads(query)
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, dict) or not {
        "schema_version", "kind", "document_id", "system_key", "object_path", "native_id"
    } & set(decoded):
        return None
    selector = decode_selector(query)
    if (
        selector["kind"] not in {"object", "property"}
        or selector["document_id"] != metadata["document_id"]
        or selector["system_key"] != metadata["system_key"]
    ):
        raise ValueError("mechanical.selector_missing: query selector belongs to another model or kind")
    return selector


def execute_search_tree(ctx, model=None, settings=None):
    if model is None:
        raise NodeInputNotReadyError("Model requires a live Mechanical model from this run")
    if not isinstance(model, RuntimeHandleRef):
        raise TypeError("Search Mechanical Tree requires a Mechanical Model")
    try:
        session = ctx.mechanical_sessions.admit_model(
            model, run_id=ctx.run_id, workspace_id=ctx.workspace_id
        )
    except StaleMechanicalModelError as exc:
        raise ValueError(f"mechanical.stale_reference: {exc}") from exc
    filter_code = str(_setting(ctx, settings, "filter", "name"))
    if filter_code not in {
        "name", "tag", "type", "state", "coordinate_system", "model", "graphics",
        "environment", "scoping", "property_name", "property_value",
    }:
        raise ValueError(f"Unknown Mechanical search filter: {filter_code}")
    query = _setting(ctx, settings, "query", "")
    if type(query) is not str:
        raise TypeError("Mechanical search Query must be text")
    match_mode = str(_setting(ctx, settings, "match", "contains"))
    if match_mode not in {"contains", "exact"}:
        raise ValueError("Mechanical search Match must be contains or exact")
    flags = {}
    for key in ("case_sensitive", "include_hidden_properties", "invert"):
        value = _setting(ctx, settings, key, False)
        if type(value) is not bool:
            raise TypeError(f"Mechanical search {key} must be Boolean")
        flags[key] = value
    metadata = model.metadata
    selector = _search_selector(query, metadata)
    identity = {
        field: metadata[field]
        for field in (
            "run_id", "session_id", "document_id", "source_key", "system_key", "model_revision"
        )
    }
    try:
        result = ctx.mechanical_sessions.operate(
            session,
            expected_revision=metadata["model_revision"],
            operation="search",
            args={
                "filter": filter_code,
                "query": query,
                "match": match_mode,
                **flags,
                "identity": identity,
                "typed_selector": selector,
            },
        )["search"]
    except StaleMechanicalModelError as exc:
        raise ValueError(f"mechanical.stale_reference: {exc}") from exc
    except Exception as exc:
        message = str(exc)
        if any(
            code in message
            for code in (
                "mechanical.search_incomplete:",
                "mechanical.capacity_exceeded:",
                "mechanical.selector_missing:",
            )
        ):
            raise ValueError(message[message.index("mechanical.") :]) from exc
        raise RuntimeError(f"mechanical.operation_failed: Search Mechanical Tree: {message}") from exc
    if (
        not isinstance(result, dict)
        or set(result) != {"objects", "properties", "details"}
        or type(result["objects"]) is not list
        or type(result["properties"]) is not list
        or type(result["details"]) is not TableValue
    ):
        raise RuntimeError("mechanical.operation_failed: Search returned an invalid result")
    for value in result["objects"]:
        validate_object(value)
        if any(value.payload[field] != identity[field] for field in identity):
            raise ValueError("mechanical.cross_session_reference: Search object belongs to another Model")
    for value in result["properties"]:
        validate_property(value)
        if any(value.payload[field] != identity[field] for field in identity):
            raise ValueError("mechanical.cross_session_reference: Search property belongs to another Model")
    return {
        **result,
        "found": bool(result["objects"] or result["properties"]),
    }


def _table_selector(value: str, metadata: Mapping[str, object]):
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, dict) or not {
        "schema_version", "kind", "document_id", "system_key", "object_path", "native_id"
    } & set(decoded):
        return None
    selector = decode_selector(value)
    if (
        selector["kind"] != "table"
        or selector["document_id"] != metadata["document_id"]
        or selector["system_key"] != metadata["system_key"]
        or type(selector["native_id"]) is not str
    ):
        raise ValueError(
            "mechanical.selector_missing: Table / property selector belongs to another model or kind"
        )
    return {
        "object_path": selector["object_path"],
        "native_id": selector["native_id"],
    }


def execute_fea_table(ctx, model=None, source=None, settings=None):
    if model is None:
        raise NodeInputNotReadyError("Model requires a live Mechanical model from this run")
    if not isinstance(model, RuntimeHandleRef):
        raise TypeError("FEA Table requires a Mechanical Model")
    try:
        session = ctx.mechanical_sessions.admit_model(
            model, run_id=ctx.run_id, workspace_id=ctx.workspace_id
        )
    except StaleMechanicalModelError as exc:
        raise ValueError(f"mechanical.stale_reference: {exc}") from exc
    if source is None:
        raise NodeInputNotReadyError("Source requires a Mechanical Object or Property")
    if type(source) not in {list, tuple}:
        raise TypeError("FEA Table Source must be a list")
    if not source:
        raise ValueError("FEA Table Source must contain at least one Object or Property")
    metadata = model.metadata
    identity_fields = (
        "run_id", "session_id", "document_id", "source_key", "system_key", "model_revision"
    )
    sources = []
    for value in source:
        if type(value) is not TypedInlineValue or value.data_type_id not in {
            OBJECT_TYPE_ID, PROPERTY_TYPE_ID
        }:
            raise TypeError("FEA Table Source accepts only Mechanical Object or Property values")
        (validate_object if value.data_type_id == OBJECT_TYPE_ID else validate_property)(value)
        if any(value.payload[field] != metadata[field] for field in identity_fields):
            raise ValueError(
                "mechanical.cross_session_reference: FEA Table source belongs to another Model"
            )
        sources.append(
            {
                "kind": "object" if value.data_type_id == OBJECT_TYPE_ID else "property",
                "object_id": value.payload["object_id"],
                "object_path": value.payload["object_path"],
                "property_key": value.payload.get("property_key", ""),
            }
        )
    family = _setting(ctx, settings, "family", "auto")
    if family not in {
        "auto", "model_definition", "result_history_summary", "spatial_samples",
        "supported_worksheet",
    }:
        raise ValueError(f"Unknown Mechanical table family: {family}")
    if family not in {"auto", "model_definition"} and any(
        value.data_type_id == PROPERTY_TYPE_ID for value in source
    ):
        raise ValueError(
            f"mechanical.table_unsupported: family {family!r} requires a Mechanical Object source"
        )
    table = _setting(ctx, settings, "table", "")
    component = _setting(ctx, settings, "component", "all")
    units = _setting(ctx, settings, "units", "source")
    if type(table) is not str or type(component) is not str:
        raise TypeError("FEA Table Table / property and Component must be text")
    if not component:
        raise ValueError("FEA Table Component must be 'all' or an exact component")
    if units not in {"source", "si"}:
        raise ValueError("FEA Table Units must be source or si")
    selector = _table_selector(table, metadata) if table else None
    result_sources = [str(value.payload.get("api_type", "")) for value in source]
    sets_active = family in {"result_history_summary", "spatial_samples"} or (
        family == "auto"
        and any(".Results." in value or value.endswith(".Solution") for value in result_sources)
    )
    sets: list[int] = []
    if sets_active:
        raw_sets = _setting(ctx, settings, "sets", [])
        if type(raw_sets) not in {list, tuple}:
            raise TypeError("FEA Table Rows / sets must be an integer list")
        if any(type(value) is not int or value <= 0 for value in raw_sets) or len(set(raw_sets)) != len(raw_sets):
            raise ValueError("FEA Table Rows / sets must contain unique positive stored-set IDs")
        sets = list(raw_sets)
    try:
        args = {
            "sources": sources,
            "family": family,
            "table": "" if selector is not None else table,
            "table_selector": selector,
            "component": component,
            "units": units,
            "native_output_path": str(
                session.work_root / f"native-definitions-{uuid4().hex}.json"
            ),
        }
        if sets_active:
            args["sets"] = sets
        response = ctx.mechanical_sessions.operate(
            session,
            expected_revision=metadata["model_revision"],
            operation="definition_tables",
            args=args,
        )
        result = response["definition_tables"]
        warnings = response.get("warnings", [])
        if type(warnings) is not list or any(type(value) is not str for value in warnings):
            raise RuntimeError("Mechanical table diagnostics are invalid")
        warn = getattr(ctx, "warn", None)
        if callable(warn):
            for warning in warnings:
                warn(warning, code="mechanical.result_state_drift")
    except StaleMechanicalModelError as exc:
        raise ValueError(f"mechanical.stale_reference: {exc}") from exc
    except Exception as exc:
        message = str(exc)
        if "Mechanical owner request exceeds encoded size limit" in message:
            raise ValueError(
                "mechanical.capacity_exceeded: source selection exceeds the owner request limit; "
                "narrow Source, Table / property, or Component"
            ) from exc
        for code in (
            "mechanical.table_unsupported:",
            "mechanical.capacity_exceeded:",
            "mechanical.selector_missing:",
            "mechanical.selector_ambiguous:",
            "mechanical.results_missing:",
            "mechanical.restore_failed:",
            "mechanical.capability_unproved:",
        ):
            if code in message:
                raise ValueError(message[message.index(code) :]) from exc
        raise RuntimeError(f"mechanical.operation_failed: FEA Table: {message}") from exc
    if (
        not isinstance(result, dict)
        or set(result) != {"tables", "definitions"}
        or type(result["tables"]) is not list
        or any(type(value) is not TableValue for value in result["tables"])
        or type(result["definitions"]) is not TableValue
    ):
        raise RuntimeError("mechanical.operation_failed: FEA Table returned invalid values")
    return result


def execute_camera_views(ctx, model=None, settings=None):
    if model is None:
        raise NodeInputNotReadyError(
            "Model requires a live Mechanical model from this run"
        )
    if not isinstance(model, RuntimeHandleRef):
        raise TypeError("Mechanical Camera Views requires a Mechanical Model")
    try:
        session = ctx.mechanical_sessions.admit_model(
            model, run_id=ctx.run_id, workspace_id=ctx.workspace_id
        )
    except StaleMechanicalModelError as exc:
        raise ValueError(f"mechanical.stale_reference: {exc}") from exc
    include = _setting(ctx, settings, "include", "saved_and_current")
    if include not in {"saved_and_current", "saved", "current"}:
        raise ValueError("Mechanical Camera Views Include is invalid")
    metadata = model.metadata
    identity = {
        field: metadata[field]
        for field in CAMERA_IDENTITY_FIELDS
    }
    try:
        result = ctx.mechanical_sessions.operate(
            session,
            expected_revision=metadata["model_revision"],
            operation="camera_views",
            args={
                "include": include,
                "identity": identity,
                "export_path": str(
                    session.work_root / f"camera-views-{uuid4().hex}.xml"
                ),
                "restore_name": f"COREX restore {uuid4().hex}",
            },
        )["camera_views"]
    except StaleMechanicalModelError as exc:
        raise ValueError(f"mechanical.stale_reference: {exc}") from exc
    except Exception as exc:
        message = str(exc)
        for code in (
            "mechanical.camera_schema_invalid:",
            "mechanical.table_unsupported:",
            "mechanical.capacity_exceeded:",
            "mechanical.restore_failed:",
            "mechanical.capability_unproved:",
        ):
            if code in message:
                raise ValueError(message[message.index(code) :]) from exc
        raise RuntimeError(
            f"mechanical.operation_failed: Mechanical Camera Views: {message}"
        ) from exc
    if (
        not isinstance(result, dict)
        or set(result) != {"views", "names", "details"}
        or type(result["views"]) is not list
        or type(result["names"]) is not list
        or len(result["views"]) != len(result["names"])
        or type(result["details"]) is not TableValue
        or result["details"].row_count != len(result["views"])
    ):
        raise RuntimeError(
            "mechanical.operation_failed: Mechanical Camera Views returned invalid values"
        )
    for index, value in enumerate(result["views"]):
        if (
            type(value) is not TypedInlineValue
            or value.data_type_id != CAMERA_VIEW_TYPE_ID
        ):
            raise RuntimeError(
                "mechanical.operation_failed: Mechanical Camera Views returned an invalid camera"
            )
        validate_camera_view(value)
        if any(value.payload[field] != identity[field] for field in identity):
            raise ValueError(
                "mechanical.cross_session_reference: Camera view belongs to another Model"
            )
        if value.payload["name"] != result["names"][index]:
            raise RuntimeError(
                "mechanical.operation_failed: Camera names do not match their views"
            )
    return result


def _image_values(value: object, label: str) -> list[object]:
    if value is None:
        return []
    if type(value) not in {list, tuple}:
        raise TypeError(f"Export Mechanical Image {label} must be a list")
    return list(value)


def _image_selector(value: object, metadata: Mapping[str, Any], *, camera: bool) -> tuple[dict[str, Any], str]:
    identity_fields = (
        "run_id", "session_id", "document_id", "source_key", "system_key", "model_revision"
    )
    if type(value) is TypedInlineValue:
        expected = CAMERA_VIEW_TYPE_ID if camera else OBJECT_TYPE_ID
        validator = validate_camera_view if camera else validate_object
        if value.data_type_id != expected or not validator(value):
            raise TypeError(
                "Export Mechanical Image accepts only Mechanical CameraView or Text values"
                if camera
                else "Export Mechanical Image accepts only Mechanical Object or Text values"
            )
        if any(value.payload[field] != metadata[field] for field in identity_fields):
            raise ValueError(
                "mechanical.cross_session_reference: image selector belongs to another Model"
            )
        if camera:
            return (
                {
                    "kind": "current" if value.payload["kind"] == "current" else "typed",
                    "index": value.payload["index"],
                    "name": value.payload["name"],
                },
                str(value.payload["name"]),
            )
        return (
            {
                "kind": "typed",
                "object_id": value.payload["object_id"],
                "object_path": value.payload["object_path"],
            },
            str(value.payload["display_name"]),
        )
    if type(value) is not str or not value.strip():
        raise TypeError("Export Mechanical Image selectors must be non-empty Text or typed values")
    text = value.strip()
    try:
        decoded = decode_selector(text) if text.startswith("{") else None
    except (TypeError, ValueError) as exc:
        raise ValueError("mechanical.selector_missing: image selector code is invalid") from exc
    if decoded is not None:
        expected_kind = "view" if camera else "object"
        if (
            decoded["kind"] != expected_kind
            or decoded["document_id"] != metadata["document_id"]
            or decoded["system_key"] != metadata["system_key"]
        ):
            raise ValueError("mechanical.selector_missing: image selector belongs to another model or kind")
        if camera:
            if decoded["native_id"] == "current":
                return {"kind": "current"}, "Current view"
            if type(decoded["native_id"]) is not int:
                raise ValueError("mechanical.selector_missing: saved view selector has an invalid index")
            return {"kind": "typed", "index": decoded["native_id"], "name": None}, f"view_{decoded['native_id']}"
        if type(decoded["native_id"]) is not int or not decoded["object_path"]:
            raise ValueError("mechanical.selector_missing: object selector has an invalid identity")
        return {
            "kind": "typed",
            "object_id": decoded["native_id"],
            "object_path": decoded["object_path"],
        }, decoded["object_path"].rsplit("/", 1)[-1]
    if camera and text == "Current view":
        return {"kind": "current"}, text
    return {"kind": "text", "text": text}, text.rsplit("/", 1)[-1]


def execute_image_export(ctx, model=None, objects=None, views=None, settings=None):
    models = _image_values(model, "Model")
    if not models:
        raise NodeInputNotReadyError("Model requires a live Mechanical model from this run")
    if len(models) != 1:
        raise ValueError(
            "Export Mechanical Image requires exactly one Model per matched branch; apply Graft to multiple Model items"
        )
    model_value = models[0]
    if not isinstance(model_value, RuntimeHandleRef):
        raise TypeError("Export Mechanical Image requires a Mechanical Model")
    try:
        session = ctx.mechanical_sessions.admit_model(
            model_value, run_id=ctx.run_id, workspace_id=ctx.workspace_id
        )
    except StaleMechanicalModelError as exc:
        raise ValueError(f"mechanical.stale_reference: {exc}") from exc
    metadata = model_value.metadata
    raw_objects = _image_values(objects, "Objects")
    raw_views = _image_values(views, "Views")
    object_selectors, object_labels = zip(
        *(_image_selector(value, metadata, camera=False) for value in raw_objects),
        strict=True,
    ) if raw_objects else (({"kind": "current"},), ("Current display",))
    view_selectors, view_labels = zip(
        *(_image_selector(value, metadata, camera=True) for value in raw_views),
        strict=True,
    ) if raw_views else (({"kind": "current"},), ("Current view",))
    capture_count = len(object_selectors) * len(view_selectors)
    if capture_count > IMAGE_CAPTURE_LIMIT:
        raise ValueError(
            f"mechanical.capacity_exceeded: requested {capture_count} image captures; maximum is {IMAGE_CAPTURE_LIMIT}"
        )
    width = _setting(ctx, settings, "width", 1600)
    height = _setting(ctx, settings, "height", 1000)
    if type(width) is not int or type(height) is not int or not 64 <= width <= 8192 or not 64 <= height <= 8192:
        raise ValueError("Mechanical image Width and Height must be integers from 64 to 8192")
    if width * height > IMAGE_MAX_PIXELS:
        raise ValueError(
            f"mechanical.capacity_exceeded: requested {width * height} pixels; maximum is {IMAGE_MAX_PIXELS}"
        )
    background = _setting(ctx, settings, "background", "white")
    if background not in {"white", "model"}:
        raise ValueError("Mechanical image Background must be white or model")
    fit_view = _setting(ctx, settings, "fit_view", False)
    if type(fit_view) is not bool:
        raise TypeError("Mechanical image Fit view must be Boolean")
    identity = {
        field: metadata[field]
        for field in (
            "run_id", "session_id", "document_id", "source_key", "system_key", "model_revision"
        )
    }
    args = {
        "objects": list(object_selectors),
        "views": list(view_selectors),
        "width": width,
        "height": height,
        "background": background,
        "fit_view": fit_view,
        "output_paths": [
            str(session.work_root / f"viewport-{uuid4().hex}.png")
            for _ in range(capture_count)
        ],
        "view_export_path": str(session.work_root / f"image-views-{uuid4().hex}.xml"),
        "restore_name": f"COREX restore {uuid4().hex}",
        "preflight_only": True,
    }
    try:
        preflight = ctx.mechanical_sessions.operate(
            session,
            expected_revision=metadata["model_revision"],
            operation="image_export",
            args=args,
        )["image_preflight"]
        preflight_records = preflight.get("images") if isinstance(preflight, dict) else None
        if type(preflight_records) is not list or len(preflight_records) != capture_count:
            raise RuntimeError("Mechanical image selector preflight returned an invalid result")
        record_fields = {
            "object_index", "object_name", "object_path", "object_id",
            "view_ordinal", "view_name", "view_kind", "view_index",
        }
        if any(
            not isinstance(record, Mapping)
            or set(record) != record_fields
            or record["object_index"] != ordinal // len(view_selectors)
            or record["view_ordinal"] != ordinal % len(view_selectors)
            or type(record["object_name"]) is not str
            or not record["object_name"]
            or type(record["view_name"]) is not str
            or not record["view_name"]
            for ordinal, record in enumerate(preflight_records)
        ):
            raise RuntimeError("Mechanical image selector preflight returned invalid records")
        labels = [
            (record["object_name"], record["view_name"])
            for record in preflight_records
        ]
        folder_value = _setting(ctx, settings, "folder", "")
        destinations: list[Path] = []
        if str(folder_value or "").strip():
            overwrite = _setting(ctx, settings, "overwrite", False)
            if type(overwrite) is not bool:
                raise TypeError("Mechanical image Overwrite must be Boolean")
            names = render_image_filenames(
                _setting(ctx, settings, "file_name", "{object}_{view}.png"),
                labels,
                view_count=len(view_selectors),
            )
            folder = ctx.resolve_path_value(folder_value)
            if folder is None:
                raise ValueError("Mechanical image Folder could not be resolved")
            destinations = preflight_image_destinations(folder, names, overwrite=overwrite)
        else:
            overwrite = False
        args["preflight_only"] = False
        response = ctx.mechanical_sessions.operate(
            session,
            expected_revision=metadata["model_revision"],
            operation="image_export",
            args=args,
        )
        result = response["image_export"]
        warnings = response.get("warnings", [])
        if type(warnings) is not list or any(type(value) is not str for value in warnings):
            raise RuntimeError("Mechanical image diagnostics are invalid")
        warn = getattr(ctx, "warn", None)
        if callable(warn):
            for warning in warnings:
                warn(warning, code="mechanical.result_state_drift")
    except StaleMechanicalModelError as exc:
        raise ValueError(f"mechanical.stale_reference: {exc}") from exc
    except Exception as exc:
        message = str(exc)
        for code in (
            "mechanical.selector_missing:",
            "mechanical.selector_ambiguous:",
            "mechanical.camera_schema_invalid:",
            "mechanical.table_unsupported:",
            "mechanical.capacity_exceeded:",
            "mechanical.restore_failed:",
            "mechanical.capability_unproved:",
        ):
            if code in message:
                raise ValueError(message[message.index(code):]) from exc
        raise RuntimeError(f"mechanical.operation_failed: Export Mechanical Image: {message}") from exc
    records = result.get("images") if isinstance(result, dict) else None
    if type(records) is not list or len(records) != capture_count:
        raise RuntimeError("mechanical.operation_failed: image capture returned an invalid result")
    images = []
    for ordinal, record in enumerate(records):
        if (
            not isinstance(record, Mapping)
            or set(record) != record_fields | {"image"}
            or {key: record[key] for key in record_fields} != dict(preflight_records[ordinal])
            or type(record["image"]) is not ImageValue
            or (record["image"].width, record["image"].height) != (width, height)
        ):
            raise RuntimeError("mechanical.operation_failed: image capture returned invalid records")
        images.append(record["image"])
    if len(images) != capture_count:
        raise RuntimeError("mechanical.operation_failed: image capture returned invalid records")
    if destinations:
        publish_image_batch(images, destinations, overwrite=overwrite)
    return build_image_outputs(
        records,
        identity=identity,
        target_path=tuple(ctx.target_path),
        target_iteration=int(ctx.target_iteration),
        file_paths=destinations,
    )


__all__ = [
    "discover_mechanical_releases",
    "execute_apdl_snippet",
    "execute_camera_views",
    "execute_fea_table",
    "execute_image_export",
    "execute_open_model",
    "execute_run_script",
    "execute_save_model",
    "execute_search_tree",
]
