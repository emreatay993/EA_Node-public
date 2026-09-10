# Purpose: Run bounded Mechanical lifecycle requests in one owned subprocess/thread.
# Map: subsystems/addons.md
# Tests: tests/mechanical_catalogue/test_owner_protocol.py, tests/mechanical_catalogue/test_image_export.py, tests/mechanical_catalogue/test_snippets.py, tests/mechanical_catalogue/test_standalone_save.py, tests/mechanical_catalogue/test_workbench_model_export.py
# Landmarks: _prepare_snippet_response; _owner_main; MechanicalOwnerProcess
from __future__ import annotations

import atexit
import ctypes
import json
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
import hashlib
import tempfile
from collections.abc import Mapping
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil

from ea_node_editor.common.payload_tools import copy_json_safe
from ea_node_editor.addons.mechanical.tables import DEFINITION_ENCODED_MAX_BYTES
from ea_node_editor.runtime_contracts.scientific_codec import (
    check_scientific_budget,
    scientific_from_payload,
    scientific_payload_size,
    scientific_to_payload,
)
from ea_node_editor.runtime_contracts.value_codec import (
    deserialize_runtime_value,
    serialize_runtime_value,
)

DEFAULT_OPERATION_TIMEOUT_SEC = 600.0
COOPERATIVE_CLOSE_TIMEOUT_SEC = 5.0
_MAX_BYTES = 1024 * 1024  # Control only; scientific/image values use COREX codecs.


class OwnerProtocolError(RuntimeError):
    pass


def _owner_command() -> list[str]:
    executable = Path(sys.executable)
    if not executable.is_file():
        raise RuntimeError("Mechanical owner subprocess executable is unavailable")
    if getattr(sys, "frozen", False):
        return [str(executable), "--private-mechanical-owner"]
    return [str(executable), "-m", __name__]


@dataclass(frozen=True, slots=True)
class OwnerIdentity:
    pid: int
    creation_time_ns: int
    transport_id: str


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("times", ctypes.c_longlong * 2),
        ("flags", wintypes.DWORD),
        ("working_set", ctypes.c_size_t * 2),
        ("active", wintypes.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority", wintypes.DWORD),
        ("scheduling", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [("values", ctypes.c_ulonglong * 6)]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", _BasicLimits),
        ("io", _IoCounters),
        ("memory", ctypes.c_size_t * 4),
    ]


class _WindowsKillJob:
    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("Mechanical owner processes currently require Windows")
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _ExtendedLimits()
        limits.basic.flags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(
            self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())

    def assign(self, process: subprocess.Popen[Any]) -> None:
        if not self.api.AssignProcessToJobObject(
            self.handle, wintypes.HANDLE(int(process._handle))
        ):
            raise ctypes.WinError(ctypes.get_last_error())

    def terminate(self) -> None:
        if self.handle and not self.api.TerminateJobObject(self.handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        handle, self.handle = getattr(self, "handle", None), None
        if handle:
            self.api.CloseHandle(handle)


def _creation_time_ns(process_handle: int | None = None) -> int:
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.GetCurrentProcess.restype = wintypes.HANDLE
    api.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    api.GetProcessTimes.restype = wintypes.BOOL
    handle = api.GetCurrentProcess() if process_handle is None else process_handle
    creation, exit_time, kernel, user = (wintypes.FILETIME() for _ in range(4))
    if not api.GetProcessTimes(
        wintypes.HANDLE(handle),
        ctypes.byref(creation),
        ctypes.byref(exit_time),
        ctypes.byref(kernel),
        ctypes.byref(user),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    ticks = (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
    return ticks * 100


def _creation_time_for_pid(pid: int) -> int:
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.restype = wintypes.HANDLE
    handle = api.OpenProcess(0x1000, False, int(pid))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return _creation_time_ns(int(handle))
    finally:
        api.CloseHandle(handle)


def _request(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = copy_json_safe(
        payload, field_name="Mechanical owner request", max_encoded_bytes=_MAX_BYTES
    )
    required = {
        "request_id",
        "run_id",
        "session_id",
        "workspace_id",
        "expected_revision",
        "operation",
        "args",
    }
    if set(value) != required:
        raise ValueError("Mechanical owner request fields are invalid")
    for field in ("request_id", "run_id", "session_id", "workspace_id", "operation"):
        item = value[field]
        if not isinstance(item, str) or not item.strip() or len(item) > 512:
            raise ValueError(f"{field} must be a bounded non-empty string")
        value[field] = item.strip()
    revision = value["expected_revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ValueError("expected_revision must be a non-negative integer")
    if not isinstance(value["args"], dict):
        raise ValueError("args must be a dictionary")
    return value


def _encode(payload: Mapping[str, Any]) -> bytes:
    encoded = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode()
    if len(encoded) > _MAX_BYTES:
        raise ValueError("Mechanical owner payload exceeds its bounded envelope")
    return encoded


def _send_encoded(stream: Any, encoded: bytes) -> None:
    stream.write(encoded + b"\n")
    stream.flush()


def _send(stream: Any, payload: Mapping[str, Any]) -> None:
    _send_encoded(stream, _encode(payload))


def _prepare_snippet_response(
    backend: Any, root: Path, request_id: str, result: dict[str, Any]
) -> bytes:
    try:
        if "rows" in result:
            result["bulk"] = _write_bulk(root, result.pop("rows"))
        encoded = _encode(
            {"request_id": request_id, "ok": True, "result": result}
        )
        backend.commit_snippet_transaction()
        return encoded
    except Exception as exc:
        try:
            backend.rollback_snippet_transaction()
        except Exception as restore_exc:
            raise RuntimeError(
                f"mechanical.restore_failed: {restore_exc}"
            ) from exc
        raise


def _receive(stream: Any) -> dict[str, Any]:
    encoded = stream.readline(_MAX_BYTES + 2)
    if not encoded:
        raise EOFError("Mechanical owner transport closed")
    if len(encoded) > _MAX_BYTES or not encoded.endswith(b"\n"):
        raise OwnerProtocolError("Mechanical owner payload framing is invalid")
    payload = json.loads(encoded)
    if not isinstance(payload, dict):
        raise OwnerProtocolError("Mechanical owner payload must be a dictionary")
    return copy_json_safe(
        payload, field_name="Mechanical owner payload", max_encoded_bytes=_MAX_BYTES
    )


def _write_bulk(root: Path, value: Any) -> dict[str, Any]:
    from ea_node_editor.addons.mechanical.contracts import catalogue_table
    payload = scientific_to_payload(catalogue_table(value))
    scientific_payload_size(payload)
    name = f"catalogue-{uuid.uuid4().hex}.json"
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    path = root / name
    path.write_bytes(encoded)
    return {"kind": "scientific", "relative_name": name, "byte_length": len(encoded), "sha256": hashlib.sha256(encoded).hexdigest()}


def _search_catalog():
    from ea_node_editor.addons.mechanical.contracts import (
        CAMERA_VIEW_TYPE_ID,
        MECHANICAL_DATA_TYPE_FAMILY,
        MECHANICAL_DATA_TYPES,
        OBJECT_TYPE_ID,
        PROPERTY_TYPE_ID,
    )
    from ea_node_editor.nodes.core_data_types import CORE_DATA_TYPE_FAMILIES, CORE_DATA_TYPES
    from ea_node_editor.runtime_contracts import DataTypeCatalog, GRAPH_DATA_TYPE_ID, TABLE_VALUE_TYPE_ID

    catalog = DataTypeCatalog()
    catalog.register_many(
        families=tuple(family for family in CORE_DATA_TYPE_FAMILIES if family.family_id in {"graph", "container"}),
        types=tuple(spec for spec in CORE_DATA_TYPES if spec.type_id in {GRAPH_DATA_TYPE_ID, TABLE_VALUE_TYPE_ID}),
        owner_id="corex.search.transport", owner_version="1", source_label="Mechanical search spool",
    )
    catalog.register_many(
        families=(MECHANICAL_DATA_TYPE_FAMILY,),
        types=tuple(
            spec
            for spec in MECHANICAL_DATA_TYPES
            if spec.type_id in {OBJECT_TYPE_ID, PROPERTY_TYPE_ID, CAMERA_VIEW_TYPE_ID}
        ),
        owner_id="mechanical.corex", owner_version="1", source_label="Mechanical search spool",
    )
    catalog.freeze()
    return catalog


def _validate_search_result(value: object, identity: Mapping[str, Any] | None = None) -> dict[str, Any]:
    from ea_node_editor.addons.mechanical.contracts import (
        SEARCH_DETAILS_COLUMNS,
        validate_object,
        validate_property,
    )
    from ea_node_editor.runtime_contracts import RuntimeArtifactRef, RuntimeHandleRef, TableValue, TypedInlineValue

    if not isinstance(value, Mapping) or set(value) != {"objects", "properties", "details"}:
        raise OwnerProtocolError("Mechanical search result schema is invalid")
    objects, properties, details = value["objects"], value["properties"], value["details"]
    if (
        type(objects) is not list
        or type(properties) is not list
        or type(details) is not TableValue
        or details.column_names != SEARCH_DETAILS_COLUMNS
        or len(objects) + len(properties) > 100_000
    ):
        raise OwnerProtocolError("Mechanical search result carriers are invalid")
    if any(isinstance(item, (RuntimeHandleRef, RuntimeArtifactRef)) for item in (*objects, *properties)):
        raise OwnerProtocolError("Mechanical search result cannot contain live references")
    try:
        for item in objects:
            if type(item) is not TypedInlineValue or not validate_object(item):
                raise TypeError
        for item in properties:
            if type(item) is not TypedInlineValue or not validate_property(item):
                raise TypeError
    except (TypeError, ValueError) as exc:
        raise OwnerProtocolError("Mechanical search result snapshot is invalid") from exc
    if identity is not None:
        fields = ("run_id", "session_id", "document_id", "source_key", "system_key", "model_revision")
        for item in (*objects, *properties):
            if any(item.payload[field] != identity[field] for field in fields):
                raise OwnerProtocolError("Mechanical search result identity does not match its current Model")
    return {"objects": objects, "properties": properties, "details": details}


def _write_search_bulk(root: Path, value: object, identity: Mapping[str, Any]) -> dict[str, Any]:
    catalog = _search_catalog()
    checked = _validate_search_result(value, identity)
    payload = serialize_runtime_value(checked, catalog=catalog)
    _validate_search_result(deserialize_runtime_value(payload, catalog=catalog), identity)
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    if len(encoded) > 384 * 1024 * 1024:
        raise ValueError("mechanical.capacity_exceeded: search transport exceeds 384 MiB")
    name = f"search-{uuid.uuid4().hex}.json"
    (root / name).write_bytes(encoded)
    return {"kind": "mechanical-search-v1", "relative_name": name, "byte_length": len(encoded), "sha256": hashlib.sha256(encoded).hexdigest()}


def _validate_definition_result(value: object) -> dict[str, Any]:
    from ea_node_editor.addons.mechanical.contracts import DEFINITIONS_COLUMNS
    from ea_node_editor.runtime_contracts import (
        DataTree,
        RuntimeArtifactRef,
        RuntimeHandleRef,
        TableValue,
    )

    if not isinstance(value, Mapping) or set(value) != {"tables", "definitions"}:
        raise OwnerProtocolError("Mechanical definition-table result schema is invalid")
    tables, definitions = value["tables"], value["definitions"]
    if (
        type(tables) is not list
        or any(type(item) is not TableValue for item in tables)
        or type(definitions) is not TableValue
        or definitions.column_names != DEFINITIONS_COLUMNS
        or any(
            isinstance(item, (DataTree, RuntimeHandleRef, RuntimeArtifactRef))
            for item in (*tables, definitions)
        )
    ):
        raise OwnerProtocolError("Mechanical definition-table carriers are invalid")
    check_scientific_budget(value)
    return {"tables": tables, "definitions": definitions}


def _write_definition_bulk(root: Path, value: object) -> dict[str, Any]:
    checked = _validate_definition_result(value)
    payload = serialize_runtime_value(checked, catalog=_search_catalog())
    _validate_definition_result(
        deserialize_runtime_value(payload, catalog=_search_catalog())
    )
    encoded = json.dumps(
        payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode()
    if len(encoded) > DEFINITION_ENCODED_MAX_BYTES:
        raise ValueError(
            "mechanical.capacity_exceeded: encoded definition output exceeds its "
            "8x scientific-operation bound; "
            "narrow Source, Table / property, or Component"
        )
    name = f"definitions-{uuid.uuid4().hex}.json"
    (root / name).write_bytes(encoded)
    return {
        "kind": "mechanical-definitions-v1",
        "relative_name": name,
        "byte_length": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _validate_camera_result(
    value: object,
    identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    from ea_node_editor.addons.mechanical.contracts import validate_camera_view
    from ea_node_editor.addons.mechanical.graphics import CAMERA_DETAILS_COLUMNS
    from ea_node_editor.runtime_contracts import (
        RuntimeArtifactRef,
        RuntimeHandleRef,
        TableValue,
        TypedInlineValue,
    )

    if not isinstance(value, Mapping) or set(value) != {"views", "names", "details"}:
        raise OwnerProtocolError("Mechanical camera result schema is invalid")
    views, names, details = value["views"], value["names"], value["details"]
    if (
        type(views) is not list
        or type(names) is not list
        or len(views) != len(names)
        or len(views) > 100_000
        or any(type(name) is not str for name in names)
        or type(details) is not TableValue
        or details.column_names != CAMERA_DETAILS_COLUMNS
        or details.row_count != len(views)
        or any(isinstance(item, (RuntimeHandleRef, RuntimeArtifactRef)) for item in views)
    ):
        raise OwnerProtocolError("Mechanical camera result carriers are invalid")
    try:
        for index, item in enumerate(views):
            if type(item) is not TypedInlineValue or not validate_camera_view(item):
                raise TypeError
            if item.payload["name"] != names[index]:
                raise ValueError
    except (TypeError, ValueError) as exc:
        raise OwnerProtocolError("Mechanical camera snapshot is invalid") from exc
    if identity is not None:
        fields = (
            "run_id",
            "session_id",
            "document_id",
            "source_key",
            "system_key",
            "model_revision",
        )
        if any(
            item.payload[field] != identity[field]
            for item in views
            for field in fields
        ):
            raise OwnerProtocolError(
                "Mechanical camera result identity does not match its current Model"
            )
    check_scientific_budget(value)
    return {"views": views, "names": names, "details": details}


def _write_camera_bulk(
    root: Path,
    value: object,
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    checked = _validate_camera_result(value, identity)
    payload = serialize_runtime_value(checked, catalog=_search_catalog())
    _validate_camera_result(
        deserialize_runtime_value(payload, catalog=_search_catalog()), identity
    )
    encoded = json.dumps(
        payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode()
    if len(encoded) > 384 * 1024 * 1024:
        raise ValueError("mechanical.capacity_exceeded: camera transport exceeds 384 MiB")
    name = f"camera-views-result-{uuid.uuid4().hex}.json"
    (root / name).write_bytes(encoded)
    return {
        "kind": "mechanical-camera-views-v1",
        "relative_name": name,
        "byte_length": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


_IMAGE_DESCRIPTOR_FIELDS = frozenset(
    {
        "object_index",
        "object_name",
        "object_path",
        "object_id",
        "view_ordinal",
        "view_name",
        "view_kind",
        "view_index",
        "relative_name",
        "byte_length",
        "sha256",
        "width",
        "height",
    }
)


def _read_image_export(
    root: Path,
    descriptor: object,
    expected_dimensions: tuple[int, int] | None = None,
) -> dict[str, Any]:
    from ea_node_editor.runtime_contracts import IMAGE_VALUE_MAX_ENCODED_BYTES, ImageValue

    if not isinstance(descriptor, Mapping) or set(descriptor) != {"images"}:
        raise OwnerProtocolError("Mechanical image descriptor schema is invalid")
    records = descriptor["images"]
    if type(records) is not list or not records or len(records) > 256:
        raise OwnerProtocolError("Mechanical image descriptor count is invalid")
    candidates: list[Path] = []
    result = []
    pairs = []
    names: set[str] = set()
    try:
        for record in records:
            if not isinstance(record, Mapping) or set(record) != _IMAGE_DESCRIPTOR_FIELDS:
                raise OwnerProtocolError("Mechanical image item descriptor schema is invalid")
            name, length, digest = (
                record["relative_name"], record["byte_length"], record["sha256"]
            )
            object_index = record["object_index"]
            view_ordinal = record["view_ordinal"]
            if (
                type(name) is not str
                or Path(name).name != name
                or not name.startswith("viewport-")
                or Path(name).suffix.casefold() != ".png"
                or type(length) is not int
                or not 0 < length <= IMAGE_VALUE_MAX_ENCODED_BYTES
                or type(digest) is not str
                or len(digest) != 64
                or name in names
                or type(object_index) is not int
                or object_index < 0
                or type(view_ordinal) is not int
                or view_ordinal < 0
                or type(record["object_name"]) is not str
                or not record["object_name"]
                or len(record["object_name"]) > 512
                or type(record["object_path"]) is not str
                or record["object_id"] is not None
                and (type(record["object_id"]) is not int or record["object_id"] < 0)
                or type(record["view_name"]) is not str
                or not record["view_name"]
                or len(record["view_name"]) > 512
                or record["view_kind"] not in {"current", "saved"}
                or record["view_kind"] == "current"
                and record["view_index"] is not None
                or record["view_kind"] == "saved"
                and (type(record["view_index"]) is not int or record["view_index"] < 0)
                or type(record["width"]) is not int
                or type(record["height"]) is not int
                or expected_dimensions is not None
                and (record["width"], record["height"]) != expected_dimensions
            ):
                raise OwnerProtocolError("Mechanical image item descriptor is invalid")
            names.add(name)
            pairs.append((object_index, view_ordinal))
            candidate = root / name
            candidates.append(candidate)
            stat = candidate.lstat()
            path = candidate.resolve()
            if (
                candidate.is_symlink()
                or bool(getattr(stat, "st_file_attributes", 0) & 0x400)
                or path.parent != root.resolve()
                or not path.is_file()
                or stat.st_size != length
            ):
                raise OwnerProtocolError("Mechanical image file is outside the owned spool")
            data = path.read_bytes()
            if len(data) != length or hashlib.sha256(data).hexdigest() != digest:
                raise OwnerProtocolError("Mechanical image file length/hash mismatch")
            image = ImageValue.from_png(data)
            if (image.width, image.height) != (record["width"], record["height"]):
                raise OwnerProtocolError("Mechanical image dimensions do not match the receipt")
            result.append(
                {
                    **{
                        key: value
                        for key, value in record.items()
                        if key not in {"relative_name", "byte_length", "sha256", "width", "height"}
                    },
                    "image": image,
                }
            )
        view_count = max(view for _object, view in pairs) + 1
        object_count = max(obj for obj, _view in pairs) + 1
        if pairs != [
            (object_index, view_ordinal)
            for object_index in range(object_count)
            for view_ordinal in range(view_count)
        ]:
            raise OwnerProtocolError("Mechanical image descriptors are not one ordered Cartesian batch")
        return {"images": result}
    except (OSError, ValueError, TypeError) as exc:
        if isinstance(exc, OwnerProtocolError):
            raise
        raise OwnerProtocolError("Mechanical image output is invalid") from exc
    finally:
        for candidate in candidates:
            candidate.unlink(missing_ok=True)


def _read_bulk(root: Path, descriptor: object):
    if not isinstance(descriptor, Mapping) or set(descriptor) != {"kind", "relative_name", "byte_length", "sha256"}:
        raise OwnerProtocolError("Mechanical bulk descriptor schema is invalid")
    name = descriptor["relative_name"]
    length = descriptor["byte_length"]
    digest = descriptor["sha256"]
    if (
        descriptor["kind"] != "scientific"
        or type(name) is not str
        or Path(name).name != name
        or type(length) is not int
        or length < 0
        or length > 384 * 1024 * 1024
        or type(digest) is not str
        or len(digest) != 64
    ):
        raise OwnerProtocolError("Mechanical bulk descriptor kind/path is invalid")
    candidate = root / name
    try:
        stat = candidate.lstat()
    except OSError as exc:
        raise OwnerProtocolError("Mechanical bulk file is unavailable") from exc
    reparse = bool(getattr(stat, "st_file_attributes", 0) & 0x400)
    path = candidate.resolve()
    if candidate.is_symlink() or reparse or path.parent != root.resolve() or not path.is_file():
        raise OwnerProtocolError("Mechanical bulk file is outside the owned spool")
    if stat.st_size != length or stat.st_size > 384 * 1024 * 1024:
        candidate.unlink(missing_ok=True)
        raise OwnerProtocolError("Mechanical bulk file length is invalid")
    try:
        data = path.read_bytes()
        if len(data) != length or hashlib.sha256(data).hexdigest() != digest:
            raise OwnerProtocolError("Mechanical bulk file length/hash mismatch")
        payload = json.loads(data)
        scientific_payload_size(payload)
        check_scientific_budget(payload)
        return scientific_from_payload(payload)
    finally:
        path.unlink(missing_ok=True)


def _read_search_bulk(root: Path, descriptor: object, identity: Mapping[str, Any]):
    if not isinstance(descriptor, Mapping) or set(descriptor) != {"kind", "relative_name", "byte_length", "sha256"}:
        raise OwnerProtocolError("Mechanical search descriptor schema is invalid")
    name, length, digest = descriptor["relative_name"], descriptor["byte_length"], descriptor["sha256"]
    if (
        descriptor["kind"] != "mechanical-search-v1"
        or type(name) is not str or Path(name).name != name or not name.startswith("search-")
        or type(length) is not int or not 0 <= length <= 384 * 1024 * 1024
        or type(digest) is not str or len(digest) != 64
    ):
        raise OwnerProtocolError("Mechanical search descriptor kind/path is invalid")
    candidate = root / name
    try:
        stat = candidate.lstat()
    except OSError as exc:
        raise OwnerProtocolError("Mechanical search bulk file is unavailable") from exc
    reparse = bool(getattr(stat, "st_file_attributes", 0) & 0x400)
    path = candidate.resolve()
    if candidate.is_symlink() or reparse or path.parent != root.resolve() or not path.is_file():
        raise OwnerProtocolError("Mechanical search bulk file is outside the owned spool")
    if stat.st_size != length:
        candidate.unlink(missing_ok=True)
        raise OwnerProtocolError("Mechanical search bulk file length is invalid")
    try:
        data = path.read_bytes()
        if len(data) != length or hashlib.sha256(data).hexdigest() != digest:
            raise OwnerProtocolError("Mechanical search bulk file length/hash mismatch")
        payload = json.loads(data)
        return _validate_search_result(
            deserialize_runtime_value(payload, catalog=_search_catalog()), identity
        )
    finally:
        path.unlink(missing_ok=True)


def _read_definition_bulk(root: Path, descriptor: object):
    if not isinstance(descriptor, Mapping) or set(descriptor) != {
        "kind", "relative_name", "byte_length", "sha256"
    }:
        raise OwnerProtocolError("Mechanical definition descriptor schema is invalid")
    name, length, digest = (
        descriptor["relative_name"],
        descriptor["byte_length"],
        descriptor["sha256"],
    )
    if (
        descriptor["kind"] != "mechanical-definitions-v1"
        or type(name) is not str
        or Path(name).name != name
        or not name.startswith("definitions-")
        or type(length) is not int
        or not 0 <= length <= DEFINITION_ENCODED_MAX_BYTES
        or type(digest) is not str
        or len(digest) != 64
    ):
        raise OwnerProtocolError("Mechanical definition descriptor kind/path is invalid")
    candidate = root / name
    try:
        stat = candidate.lstat()
    except OSError as exc:
        raise OwnerProtocolError("Mechanical definition bulk file is unavailable") from exc
    reparse = bool(getattr(stat, "st_file_attributes", 0) & 0x400)
    path = candidate.resolve()
    if (
        candidate.is_symlink()
        or reparse
        or path.parent != root.resolve()
        or not path.is_file()
        or stat.st_size != length
    ):
        candidate.unlink(missing_ok=True)
        raise OwnerProtocolError("Mechanical definition bulk file is invalid")
    try:
        data = path.read_bytes()
        if len(data) != length or hashlib.sha256(data).hexdigest() != digest:
            raise OwnerProtocolError("Mechanical definition bulk file length/hash mismatch")
        return _validate_definition_result(
            deserialize_runtime_value(json.loads(data), catalog=_search_catalog())
        )
    finally:
        path.unlink(missing_ok=True)


def _read_camera_bulk(
    root: Path,
    descriptor: object,
    identity: Mapping[str, Any],
):
    if not isinstance(descriptor, Mapping) or set(descriptor) != {
        "kind",
        "relative_name",
        "byte_length",
        "sha256",
    }:
        raise OwnerProtocolError("Mechanical camera descriptor schema is invalid")
    name, length, digest = (
        descriptor["relative_name"],
        descriptor["byte_length"],
        descriptor["sha256"],
    )
    if (
        descriptor["kind"] != "mechanical-camera-views-v1"
        or type(name) is not str
        or Path(name).name != name
        or not name.startswith("camera-views-result-")
        or type(length) is not int
        or not 0 <= length <= 384 * 1024 * 1024
        or type(digest) is not str
        or len(digest) != 64
    ):
        raise OwnerProtocolError("Mechanical camera descriptor kind/path is invalid")
    candidate = root / name
    try:
        stat = candidate.lstat()
    except OSError as exc:
        raise OwnerProtocolError("Mechanical camera bulk file is unavailable") from exc
    reparse = bool(getattr(stat, "st_file_attributes", 0) & 0x400)
    path = candidate.resolve()
    if (
        candidate.is_symlink()
        or reparse
        or path.parent != root.resolve()
        or not path.is_file()
        or stat.st_size != length
    ):
        candidate.unlink(missing_ok=True)
        raise OwnerProtocolError("Mechanical camera bulk file is invalid")
    try:
        data = path.read_bytes()
        if len(data) != length or hashlib.sha256(data).hexdigest() != digest:
            raise OwnerProtocolError("Mechanical camera bulk file length/hash mismatch")
        return _validate_camera_result(
            deserialize_runtime_value(json.loads(data), catalog=_search_catalog()),
            identity,
        )
    finally:
        path.unlink(missing_ok=True)


def _child(port: int, token: str, spool_root: str) -> int:
    connection = socket.create_connection(("127.0.0.1", port), timeout=10)
    stream = connection.makefile("rwb", buffering=0)
    _send(
        stream,
        {
            "type": "connected",
            "token": token,
            "pid": os.getpid(),
            "creation_time_ns": _creation_time_ns(),
        },
    )
    if _receive(stream) != {"type": "start", "token": token}:
        return 2
    connection.settimeout(None)
    # Native imports happen only after the parent assigns the kill-on-close job.
    from ea_node_editor.addons.mechanical.backend import MechanicalOwnerBackend

    scope = None
    backend = MechanicalOwnerBackend()
    try:
        while True:
            request = _request(_receive(stream))
            try:
                request_scope = (
                    request["run_id"],
                    request["session_id"],
                    request["workspace_id"],
                )
                if request["operation"] != "close":
                    if scope is None:
                        scope = request_scope
                    elif scope != request_scope:
                        raise ValueError(
                            "Mechanical owner request identity does not match its session"
                        )
                result = backend.execute(request["operation"], request["args"])
                if request["operation"] == "run_snippet":
                    encoded = _prepare_snippet_response(
                        backend,
                        Path(spool_root),
                        request["request_id"],
                        result,
                    )
                    _send_encoded(stream, encoded)
                    continue
                if "rows" in result:
                    rows = result.pop("rows")
                    result["bulk"] = _write_bulk(Path(spool_root), rows)
                if "search" in result:
                    search = result.pop("search")
                    result["search_bulk"] = _write_search_bulk(
                        Path(spool_root), search, request["args"]["identity"]
                    )
                if "definition_tables" in result:
                    definitions = result.pop("definition_tables")
                    result["definition_bulk"] = _write_definition_bulk(
                        Path(spool_root), definitions
                    )
                if "camera_views" in result:
                    camera_views = result.pop("camera_views")
                    result["camera_bulk"] = _write_camera_bulk(
                        Path(spool_root), camera_views, request["args"]["identity"]
                    )
                response = {
                    "request_id": request["request_id"],
                    "ok": True,
                    "result": result,
                }
                _send(stream, response)
            except Exception as exc:  # noqa: BLE001
                if request["operation"] == "run_snippet":
                    try:
                        backend.rollback_snippet_transaction()
                    except Exception as restore_exc:  # noqa: BLE001
                        exc = RuntimeError(f"mechanical.restore_failed: {restore_exc}")
                _send(
                    stream,
                    {
                        "request_id": request["request_id"],
                        "ok": False,
                        "error": str(exc),
                    },
                )
            if request["operation"] == "close":
                return 0
    except (EOFError, OSError):
        return 0
    finally:
        try:
            backend.close()
        finally:
            stream.close()
            connection.close()


class MechanicalOwnerProcess:
    def __init__(self, *, start_timeout_sec: float = 10.0, work_root: Path | str | None = None) -> None:
        self._temporary_spool = work_root is None
        self._spool_root = Path(work_root or tempfile.mkdtemp(prefix="corex-mechanical-owner-")).resolve()
        self._spool_root.mkdir(parents=True, exist_ok=True)
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(start_timeout_sec)
        token = uuid.uuid4().hex
        flags = getattr(subprocess, "CREATE_SUSPENDED", 4) | getattr(
            subprocess, "CREATE_NO_WINDOW", 0
        )
        process = subprocess.Popen(
            [
                *_owner_command(),
                "--owner-child",
                str(listener.getsockname()[1]),
                token,
                str(self._spool_root),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        job = _WindowsKillJob()
        connection = stream = None
        try:
            job.assign(process)
            status = ctypes.WinDLL("ntdll").NtResumeProcess(
                wintypes.HANDLE(int(process._handle))
            )
            if status:
                raise OSError(int(status), "NtResumeProcess failed")
            connection, _ = listener.accept()
            connection.settimeout(start_timeout_sec)
            stream = connection.makefile("rwb", buffering=0)
            ready = _receive(stream)
            owner_pid = int(ready["pid"])
            actual_creation = _creation_time_for_pid(owner_pid)
            self.identity = OwnerIdentity(
                owner_pid, int(ready["creation_time_ns"]), token
            )
            parent_pids = {parent.pid for parent in psutil.Process(owner_pid).parents()}
            if (
                ready.get("token") != token
                or process.pid not in parent_pids
                or self.identity.creation_time_ns != actual_creation
            ):
                raise OwnerProtocolError(
                    "Mechanical owner identity handshake failed: "
                    f"{self.identity!r} not owned by ({process.pid}, {actual_creation}, {token})"
                )
            _send(stream, {"type": "start", "token": token})
        except BaseException:
            job.terminate()
            process.wait(timeout=2)
            job.close()
            if stream is not None:
                stream.close()
            if connection is not None:
                connection.close()
            raise
        finally:
            listener.close()
        self._process, self._job = process, job
        self._connection, self._stream = connection, stream
        self._lock, self._close_lock = threading.Lock(), threading.Lock()
        self._closed, self._scope = False, None
        atexit.register(self.close)

    @property
    def alive(self) -> bool:
        if self._closed:
            return False
        try:
            process = psutil.Process(self.identity.pid)
            return (
                process.is_running()
                and process.status() != psutil.STATUS_ZOMBIE
                and _creation_time_for_pid(self.identity.pid)
                == self.identity.creation_time_ns
            )
        except (OSError, psutil.Error):
            return False

    def request(
        self,
        *,
        run_id: str,
        session_id: str,
        workspace_id: str,
        expected_revision: int,
        operation: str,
        args: Mapping[str, Any] | None = None,
        timeout_sec: float = DEFAULT_OPERATION_TIMEOUT_SEC,
    ) -> dict[str, Any]:
        request_id = uuid.uuid4().hex
        payload = _request(
            {
                "request_id": request_id,
                "run_id": run_id,
                "session_id": session_id,
                "workspace_id": workspace_id,
                "expected_revision": expected_revision,
                "operation": operation,
                "args": dict(args or {}),
            }
        )
        with self._lock:
            if not self.alive:
                raise OwnerProtocolError("Mechanical owner process is closed")
            scope = (payload["run_id"], payload["session_id"], payload["workspace_id"])
            if self._scope is None:
                self._scope = scope
            elif self._scope != scope:
                raise OwnerProtocolError(
                    "Mechanical owner request identity does not match its session"
                )
            try:
                self._connection.settimeout(timeout_sec)
                _send(self._stream, payload)
                response = _receive(self._stream)
            except socket.timeout as exc:
                self.close()
                raise TimeoutError(
                    f"Mechanical owner operation {operation!r} timed out"
                ) from exc
            except (EOFError, OSError) as exc:
                raise OwnerProtocolError("Mechanical owner transport closed") from exc
        if response.get("request_id") != request_id:
            self.close()
            raise OwnerProtocolError("Mechanical owner response identity mismatch")
        if response.get("ok") is not True:
            raise OwnerProtocolError(
                str(response.get("error", "Mechanical owner operation failed"))
            )
        result = response.get("result")
        if not isinstance(result, dict):
            raise OwnerProtocolError("Mechanical owner result must be a dictionary")
        if "bulk" in result:
            result["catalogue"] = _read_bulk(self._spool_root, result.pop("bulk"))
        if "search_bulk" in result:
            result["search"] = _read_search_bulk(
                self._spool_root, result.pop("search_bulk"), payload["args"]["identity"]
            )
        if "definition_bulk" in result:
            result["definition_tables"] = _read_definition_bulk(
                self._spool_root, result.pop("definition_bulk")
            )
        if "camera_bulk" in result:
            result["camera_views"] = _read_camera_bulk(
                self._spool_root,
                result.pop("camera_bulk"),
                payload["args"]["identity"],
            )
        if "image_export" in result:
            result["image_export"] = _read_image_export(
                self._spool_root,
                result["image_export"],
                (payload["args"]["width"], payload["args"]["height"]),
            )
        return result

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            if self.alive:
                try:
                    self._connection.settimeout(COOPERATIVE_CLOSE_TIMEOUT_SEC)
                    _send(
                        self._stream,
                        _request(
                            {
                                "request_id": uuid.uuid4().hex,
                                "run_id": "cleanup",
                                "session_id": "cleanup",
                                "workspace_id": "cleanup",
                                "expected_revision": 0,
                                "operation": "close",
                                "args": {},
                            }
                        ),
                    )
                    deadline = time.monotonic() + COOPERATIVE_CLOSE_TIMEOUT_SEC
                    while self.alive and time.monotonic() < deadline:
                        time.sleep(0.02)
                    if self.alive:
                        raise subprocess.TimeoutExpired(
                            "mechanical-owner", COOPERATIVE_CLOSE_TIMEOUT_SEC
                        )
                except (EOFError, OSError, socket.timeout, subprocess.TimeoutExpired):
                    self._job.terminate()
                    deadline = time.monotonic() + 2.0
                    while self.alive and time.monotonic() < deadline:
                        time.sleep(0.02)
            if self.alive:
                raise RuntimeError("Mechanical owner process did not terminate")
            self._stream.close()
            self._connection.close()
            self._job.close()
            self._closed = True
            atexit.unregister(self.close)
            for path in (
                *self._spool_root.glob("catalogue-*.json"),
                *self._spool_root.glob("search-*.json"),
                *self._spool_root.glob("definitions-*.json"),
                *self._spool_root.glob("camera-views-result-*.json"),
            ):
                if path.is_file() and not path.is_symlink():
                    path.unlink(missing_ok=True)
            if self._temporary_spool:
                import shutil
                shutil.rmtree(self._spool_root, ignore_errors=True)


def _main() -> int:
    return (
        _child(int(sys.argv[2]), sys.argv[3], sys.argv[4])
        if len(sys.argv) == 5 and sys.argv[1] == "--owner-child"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "COOPERATIVE_CLOSE_TIMEOUT_SEC",
    "DEFAULT_OPERATION_TIMEOUT_SEC",
    "MechanicalOwnerProcess",
    "OwnerIdentity",
    "OwnerProtocolError",
]
